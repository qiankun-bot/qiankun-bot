"""
Simple my.telegram.org proxy — deployed on Render
Access: https://qiankun-bot.onrender.com/tg
"""
from flask import Flask, request, Response
import requests

app = Flask(__name__)

TG_URL = "https://my.telegram.org"

@app.route("/tg/", defaults={"path": ""})
@app.route("/tg/<path:path>")
def proxy(path=""):
    url = f"{TG_URL}/{path}"
    
    # Forward method, headers, data
    headers = {}
    for k, v in request.headers:
        if k.lower() not in ("host", "content-length", "content-encoding"):
            headers[k] = v
    
    # Add referer
    headers["Referer"] = TG_URL
    
    try:
        if request.method == "POST":
            resp = requests.post(
                url, 
                data=request.form,
                headers=headers,
                cookies=request.cookies,
                allow_redirects=True,
                timeout=30
            )
        else:
            resp = requests.get(
                url,
                headers=headers,
                cookies=request.cookies,
                allow_redirects=True,
                timeout=30
            )
        
        # Forward response
        excluded = ("content-encoding", "transfer-encoding", "content-length")
        resp_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        
        return Response(
            resp.content,
            status=resp.status_code,
            headers=dict(resp_headers),
            content_type=resp.headers.get("content-type", "text/html")
        )
    except Exception as e:
        return f"Proxy error: {e}"

if __name__ == "__main__":
    print("TG Proxy on port 10003")
    app.run(host="0.0.0.0", port=10003)
