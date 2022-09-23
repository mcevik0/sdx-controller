#!/usr/bin/env python3

import logging
import os
import json

from bapm_consumer import *
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)
logging.getLogger("pika").setLevel(logging.WARNING)

ES_HOST = "localhost"
ES_PORT = 9200
MQ_HOST = "amqp://guest:guest@aw-sdx-monitor.renci.org:5672/%2F"


def is_json(myjson):
    try:
        json.loads(myjson)
    except ValueError as e:
        return False
    return True


def start_consumer(thread_queue, es):
    MSG_ID = 1
    consumer = BAPMConsumer(MQ_HOST, thread_queue)

    t1 = threading.Thread(target=consumer.run, args=())
    t1.start()

    while True:
        if not thread_queue.empty():
            data = thread_queue.get()
            if is_json(data):
                resp = es.index(index="measurement-index", id=MSG_ID, document=data)
                print(resp["result"])
                MSG_ID += 1
            else:
                logger.info("Received non-JSON data. Not saving to ElasticSearch.")


def main():
    logging.basicConfig(level=logging.INFO)

    es = Elasticsearch([{"host": ES_HOST, "port": ES_PORT}])

    thread_queue = Queue()
    start_consumer(thread_queue, es)


if __name__ == "__main__":
    main()
