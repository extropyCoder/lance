from flask import Flask, request

app = Flask(__name__)


@app.route("/search")
def search():
    q = request.args.get("q")
    query = "SELECT name FROM items WHERE name = " + q
    cursor.execute(query)
