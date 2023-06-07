#!/usr/bin/env python3

import json
import logging
import threading

import connexion
from sdx.pce.load_balancing.te_solver import TESolver
from sdx.pce.topology.manager import TopologyManager
from sdx.pce.topology.temanager import TEManager

from swagger_server import encoder
from swagger_server.messaging.rpc_queue_consumer import *
from swagger_server.messaging.topic_queue_producer import TopicQueueProducer
from swagger_server.utils.db_utils import *

logger = logging.getLogger(__name__)
logging.getLogger("pika").setLevel(logging.WARNING)


def is_json(myjson):
    try:
        json.loads(myjson)
    except ValueError as e:
        return False
    return True


def find_between(s, first, last):
    try:
        start = s.index(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        return ""


def generate_breakdown_and_send_to_lc(connection_data, link_connection_dict, db_instance):
    temanager = TEManager(topology_data=None, connection_data=connection_data)
    num_domain_topos = 0

    if db_instance.read_from_db("num_domain_topos") is not None:
        num_domain_topos = db_instance.read_from_db("num_domain_topos")[
            "num_domain_topos"
        ]
    lc_domain_topo_dict = {}

    # Read LC-1, LC-2, LC-3, and LC-4 topologies because of
    # https://github.com/atlanticwave-sdx/sdx-controller/issues/152
    for i in range(1, int(num_domain_topos) + 1):
        lc = f"LC-{i}"
        logger.debug(f"Reading {lc} from DB")
        curr_topo = db_instance.read_from_db(lc)
        if curr_topo is None:
            logger.debug(f"Read {lc} from DB: {curr_topo}")
            continue
        else:
            # Get the actual thing minus the Mongo ObjectID.
            curr_topo_str = curr_topo.get(lc)
            # Just print a substring, not the whole thing.
            logger.debug(f"Read {lc} from DB: {curr_topo_str[0:50]}...")

        curr_topo_json = json.loads(curr_topo_str)
        lc_domain_topo_dict[curr_topo_json["domain_name"]] = curr_topo_json[
            "lc_queue_name"
        ]
        logger.debug(f"Adding #{i} topology {curr_topo_json.get('id')} to TEManager")
        temanager.add_topology(curr_topo_json)

    graph = temanager.generate_graph_te()
    if graph is None:
        return

    traffic_matrix = temanager.generate_connection_te()
    if traffic_matrix is None:
        return

    solver = TESolver(graph, traffic_matrix)
    solution = solver.solve()
    if solution is None or solution.connection_map is None:
        return

    breakdown = temanager.generate_connection_breakdown(solution)
    logger.debug(f"-- BREAKDOWN: {json.dumps(breakdown)}")

    if breakdown is None:
        return
    
    for domain, link in breakdown.items():
        link_str = json.dumps(link)
        if link_str not in link_connection_dict:
            link_connection_dict[link_str] = set()
        elif body in link_connection_dict[link_str]:
            link_connection_dict[link_str].remove(body)

        db_instance.add_key_value_pair_to_db(
            "link_connection_dict", json.dumps(link_connection_dict)
        )

        logger.debug(f"Attempting to publish domain: {domain}, link: {link}")

        # From "urn:ogf:network:sdx:topology:amlight.net", attempt to
        # extract a string like "amlight".
        domain_name = find_between(domain, "topology:", ".net") or f"{domain}"
        exchange_name = "connection"

        logger.debug(
            f"Publishing '{link}' with exchange_name: {exchange_name}, "
            f"routing_key: {domain_name}"
        )

        producer = TopicQueueProducer(
            timeout=5, exchange_name=exchange_name, routing_key=domain_name
        )
        producer.call(json.dumps(link))
        producer.stop_keep_alive()


def handle_link_failure(msg_json, db_instance):
    logger.debug("Removing connections that contain failed link")
    if db_instance.read_from_db("link_connection_dict") is None:
        return
    link_connection_dict_str = db_instance.read_from_db("link_connection_dict")[
        "link_connection_dict"
    ]
    link_connection_dict = json.loads(link_connection_dict_str)
    for link in link_connection_dict:
        connection_data = link_connection_dict[link]
        if connection_data:
            generate_breakdown_and_send_to_lc(connection_data, link_connection_dict, db_instance)


def process_lc_json_msg(
    msg,
    db_instance,
    latest_topo,
    domain_list,
    manager,
    num_domain_topos,
):
    logger.info("MQ received message:" + str(msg))
    msg_json = json.loads(msg)
    msg_id = msg_json["id"]
    msg_version = msg_json["version"]

    lc_queue_name = msg_json["lc_queue_name"]
    logger.debug("---lc_queue_name:---")
    logger.debug(lc_queue_name)

    domain_name = find_between(msg_id, "topology:", ".net")
    msg_json["domain_name"] = domain_name

    db_msg_id = str(msg_id) + "-" + str(msg_version)
    # add message to db
    db_instance.add_key_value_pair_to_db(db_msg_id, msg)
    logger.info("Save to database complete.")
    logger.info("message ID:" + str(db_msg_id))

    # Update existing topology
    if domain_name in domain_list:
        logger.info("updating topo")
        manager.update_topology(msg_json)
        if "link_failure" in msg_json:
            handle_link_failure(msg_json)
    # Add new topology
    else:
        domain_list.append(domain_name)
        db_instance.add_key_value_pair_to_db("domain_list", domain_list)

        logger.info("adding topo")
        manager.add_topology(msg_json)

        if db_instance.read_from_db("num_domain_topos") is None:
            num_domain_topos = 1
            db_instance.add_key_value_pair_to_db("num_domain_topos", num_domain_topos)
        else:
            num_domain_topos = len(domain_list)
            num_domain_topos = int(num_domain_topos) + 1
            db_instance.add_key_value_pair_to_db("num_domain_topos", num_domain_topos)

    logger.info("adding topo to db:")
    db_key = "LC-" + str(num_domain_topos)
    db_instance.add_key_value_pair_to_db(db_key, json.dumps(msg_json))

    latest_topo = json.dumps(manager.get_topology().to_dict())
    # use 'latest_topo' as PK to save latest topo to db
    db_instance.add_key_value_pair_to_db("latest_topo", latest_topo)
    logger.info("Save to database complete.")


def start_consumer(thread_queue, db_instance):
    MESSAGE_ID = 0
    HEARTBEAT_ID = 0
    rpc = RpcConsumer(thread_queue, "")
    t1 = threading.Thread(target=rpc.start_consumer, args=())
    t1.start()

    manager = TopologyManager()

    latest_topo = {}
    domain_list = []

    if db_instance.read_from_db("domain_list") is not None:
        domain_list = db_instance.read_from_db("domain_list")["domain_list"]

    num_domain_topos = len(domain_list)

    if db_instance.read_from_db("num_domain_topos") is not None:
        db_instance.add_key_value_pair_to_db("num_domain_topos", num_domain_topos)
        for topo in range(1, num_domain_topos + 1):
            db_key = f"LC-{topo}"
            logger.debug(f"Reading {db_key} from DB")
            topology = db_instance.read_from_db(db_key)
            logger.debug(f"Read {db_key}: {topology}")
            if topology is None:
                continue
            else:
                # Get the actual thing minus the Mongo ObjectID.
                topology = topology[db_key]
            topo_json = json.loads(topology)
            manager.add_topology(topo_json)

    while True:
        if thread_queue.empty():
            continue

        msg = thread_queue.get()
        logger.debug("MQ received message:" + str(msg))

        if "Heart Beat" in str(msg):
            HEARTBEAT_ID += 1
            logger.debug("Heart beat received. ID: " + str(HEARTBEAT_ID))
        else:
            logger.info("Saving to database.")
            if is_json(msg):
                if "version" in str(msg):
                    process_lc_json_msg(
                        msg,
                        db_instance,
                        latest_topo,
                        domain_list,
                        manager,
                        num_domain_topos,
                    )
                else:
                    logger.info("got message from MQ: " + str(msg))
            else:
                db_instance.add_key_value_pair_to_db(str(MESSAGE_ID), msg)
                logger.debug("Save to database complete.")
                logger.debug("message ID:" + str(MESSAGE_ID))
                value = db_instance.read_from_db(str(MESSAGE_ID))
                logger.debug("got value from DB:")
                logger.debug(value)
                MESSAGE_ID += 1


def main():
    logging.basicConfig(level=logging.INFO)

    # Run swagger service
    app = connexion.App(__name__, specification_dir="./swagger/")
    app.app.json_encoder = encoder.JSONEncoder
    app.add_api(
        "swagger.yaml", arguments={"title": "SDX-Controller"}, pythonic_params=True
    )

    # Run swagger in a thread
    threading.Thread(target=lambda: app.run(port=8080)).start()

    DB_NAME = os.environ.get("DB_NAME") + ".sqlite3"

    # Get DB connection and tables set up.
    db_instance = DbUtils()
    db_instance.initialize_db()

    thread_queue = Queue()
    start_consumer(thread_queue, db_instance)


if __name__ == "__main__":
    main()
