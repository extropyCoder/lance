from flask import Flask, request
import os
app = Flask(__name__)

@app.route("/ping")
def ping():
    helper()

def helper():
    host = request.args.get("host")
    os.system(f"ping {host}")
