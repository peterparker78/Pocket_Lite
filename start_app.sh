#!/bin/bash
cd /Users/zahidbashir/Documents/Projects/Pocket_Lite
source venv/bin/activate
export FLASK_DEBUG=0
export PYTHONUNBUFFERED=1
python -c "
from app import app, db
with app.app_context():
    db.create_all()
app.run(host='127.0.0.1', port=5003, threaded=True)
" >> logs/app.log 2>&1
