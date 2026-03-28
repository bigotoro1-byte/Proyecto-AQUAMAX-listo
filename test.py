from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>FUNCIONA FLASK</h1>"

@app.route("/productos")
def productos():
    return "<h1>FUNCIONA PRODUCTOS</h1>"

if __name__ == "__main__":
    print("🔥 INICIANDO APP...")
    app.run(debug=True)