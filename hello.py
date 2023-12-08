from flask import Flask, render_template, url_for, request, send_file
from fileinput import filename
app = Flask(__name__)

@app.route('/', methods = ['POST', 'GET'])
def index():
  if request.method == "POST":
    f = request.files['file']
    return send_file(f, mimetype='video/mov')
  else:
    return render_template('index.html')

if __name__ == '__main__':
  app.run(debug = True, port=3000)