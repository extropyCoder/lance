from flask import Flask, request
import subprocess

app = Flask(__name__)


@app.route("/ping")
def ping():
    host = request.args.get("host")
    subprocess.run(["ping", host])
