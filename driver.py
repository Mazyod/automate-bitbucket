import os
import json
import requests
from flask import Flask, Response, request


""" app creation """
app = Flask(__name__)
app.config.from_object(__name__)


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
    print(f"Process event: {event}")
    payload = request.get_json()
    response = Response(status=200)

    if not isinstance(payload, dict):
        return response

    if event in comment_events:
        handle_comment(payload)

    process_tasks(payload)

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
    pr = payload.get("pullrequest")
    if not isinstance(pr, dict):
        print(f"No PR found: {payload}")
        return

    merge_link = pr["links"]["merge"]["href"]
    approve_link = pr["links"]["approve"]["href"]

    print(f"merge: {merge_link}")
    print(f"approve: {approve_link}")

    config = config_file()
    auth = (config["creds"]["user"], config["creds"]["pass"])
    tasks = tasks_file()

    def clean_link(response, key, link):
        if response.status_code not in range(200, 300):
            return

        tasks[key].remove(link)
        tasks_file(tasks)

    if approve_link in tasks["approve"]:
        response = requests.post(approve_link, auth=auth)
        print(response)
    if merge_link in tasks["merge"]:
        response = requests.post(merge_link, auth=auth)
        clean_link(response, "merge", merge_link)
        print(response)


def handle_comment(payload):

    config = config_file()
    comment = payload["comment"]
    user = comment["user"]["account_id"]

    if user not in config["users"]:
        return

    tasks = tasks_file()
    text = comment["content"]["raw"]
    pr_links = payload["pullrequest"]["links"]

    if text == "auto-merge please":
        merge = pr_links["merge"]["href"]
        tasks["merge"].append(merge)
    elif text == "auto-approve please":
        approve = pr_links["approve"]["href"]
        tasks["approve"].append(approve)
    else:
        return

    tasks_file(tasks)


def main():
    app.run(host='0.0.0.0', port=8448, debug=False)


if __name__ == '__main__':
    main()
