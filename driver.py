import os
import re
import json
import requests
import logging
from threading import Thread
from queue import Queue
from flask import Flask, Response, request


logging.basicConfig(level=logging.DEBUG)


""" app creation """
app = Flask(__name__)
app.config.from_object(__name__)


task_queue = Queue()

tasks_file_template = {
    "approve": [],
    "merge": []
}

comment_events = [
    "pullrequest:comment_created",
    "pullrequest:comment_updated",
]


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():

    event = request.headers.get("X-Event-Key")
    logging.debug(f"Process event: {event}")
    payload = request.get_json()
    response = Response(status=200)

    if not isinstance(payload, dict):
        return response

    if event in comment_events:
        handle_comment(payload)

    task_queue.put_nowait(payload)

    return response


def config_file():
    filename = "config.json"
    with open(filename) as f:
        return json.load(f)


def tasks_file(new_value=None):
    filename = "tasks.json"
    if new_value or not os.path.exists(filename):
        obj = new_value or tasks_file_template
        with open(filename, "w+") as f:
            json.dump(obj, f, indent=2)

    if new_value:
        return new_value

    with open(filename) as f:
        return json.load(f)


def process_tasks(payload):

    config = config_file()
    creds = config["creds"]
    tasks = tasks_file()

    def clean_link(response, key, link):
        if response.status_code not in range(200, 300):
            return

        tasks[key].remove(link)
        tasks_file(tasks)

    for approve_task in tasks["approve"]:
        auth = creds[approve_task[0]]
        approve_link = approve_task[1]
        response = requests.post(approve_link, auth=(auth["user"], auth["pass"]))
        logging.debug(f"Response: {response}")

    for merge_task in tasks["merge"]:
        auth = creds[merge_task[0]]
        merge_link = merge_task[1]
        response = requests.post(merge_link, auth=(auth["user"], auth["pass"]))
        clean_link(response, "merge", merge_task)
        logging.debug(f"Response: {response}")

    if "admin" in tasks:
        uuid = tasks["admin"]
        maz = creds["557058:d04761dc-a1ab-43d5-8456-fbaf8da7d6d1"]
        auth = (maz["user"], maz["pass"])
        logging.debug(f"Make admin: {uuid}")

        make_icma_admin(uuid, auth)
        del tasks["admin"]
        tasks_file(tasks)


def handle_comment(payload):

    config = config_file()
    comment = payload["comment"]
    user = comment["user"]["account_id"]

    if user not in config["creds"].keys():
        user = None

    tasks = tasks_file()
    text = comment["content"]["raw"]
    pr_links = payload["pullrequest"]["links"]

    if user and text == "auto-merge please":
        merge = pr_links["merge"]["href"]
        tasks["merge"].append([user, merge])
    elif user and text == "auto-approve please":
        approve = pr_links["approve"]["href"]
        tasks["approve"].append([user, approve])
    elif text == "I am on call please":
        uuid = comment["user"]["uuid"]
        tasks["admin"] = uuid
    else:
        return

    tasks_file(tasks)


def make_icma_admin(user_uuid, auth):
    # make sure to update "push" first
    rules = [
        "5799241", # develop: push
        "5818583", # master: push
        "6143297", # master: merge
        "5818598", # hotfix/*: push
        "6143288", # hotfix/*: merge
        "5799249", # release/*: push
        "6143300", # release/*: merge
    ]

    for rule in rules:
        logging.debug(f"Updating rule: {rule}")
        response = requests.put((
            "https://api.bitbucket.org/2.0/repositories/careemteam/icma/"
            f"branch-restrictions/{rule}"),
            auth=auth,
            json={"users": [{"uuid": user_uuid}]})
        logging.debug(f"Response: {response}")


def tasks_worker():
    while True:
        try:
            payload = task_queue.get()
        except:
            break
        process_tasks(payload)


def main():

    tasks_thread = Thread(target=tasks_worker)
    tasks_thread.daemon = True
    tasks_thread.start()

    app.run(host='0.0.0.0', port=8448, debug=True)


if __name__ == '__main__':
    main()
