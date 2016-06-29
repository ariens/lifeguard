#!./python/bin/python
# Runs the native flask app locally in stand-alone debug mode

from app import app
if __name__ == "__main__":
    app.run(host='localhost', debug=True)
