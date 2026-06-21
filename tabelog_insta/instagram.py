import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class InstagramClient:
    def __init__(self, config):
        instagram = config.get("instagram", {})
        self.graph_version = instagram.get("graph_version", "v24.0")
        self.ig_user_id = instagram.get("ig_user_id", "")
        self.access_token = instagram.get("access_token", "")

    @property
    def ready(self):
        return bool(self.ig_user_id and self.access_token)

    def _post(self, path, params):
        if not self.ready:
            raise RuntimeError("Instagram credentials are not configured.")
        params = dict(params)
        params["access_token"] = self.access_token
        url = f"https://graph.facebook.com/{self.graph_version}/{path}"
        data = urlencode(params).encode("utf-8")
        req = Request(url, data=data, method="POST")
        try:
            with urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Instagram API error {exc.code}: {body}") from exc

    def _get(self, path, params):
        if not self.ready:
            raise RuntimeError("Instagram credentials are not configured.")
        params = dict(params)
        params["access_token"] = self.access_token
        url = f"https://graph.facebook.com/{self.graph_version}/{path}?{urlencode(params)}"
        req = Request(url, method="GET")
        try:
            with urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Instagram API error {exc.code}: {body}") from exc

    def create_media(self, **params):
        return self._post(f"{self.ig_user_id}/media", params)

    def media_status(self, creation_id):
        return self._get(creation_id, {"fields": "status_code,status"})

    def wait_for_media(self, creation_id, timeout=120, interval=5):
        deadline = time.time() + timeout
        last_status = {}
        while time.time() < deadline:
            last_status = self.media_status(creation_id)
            status_code = last_status.get("status_code")
            if status_code in {"FINISHED", "PUBLISHED"}:
                return last_status
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram media container is not publishable: {last_status}")
            time.sleep(interval)
        raise RuntimeError(f"Instagram media container was not ready in time: {last_status}")

    def publish_media(self, creation_id, wait=True):
        if wait:
            self.wait_for_media(creation_id)
        return self._post(f"{self.ig_user_id}/media_publish", {"creation_id": creation_id})

    def publish_feed(self, image_url, caption):
        container = self.create_media(image_url=image_url, caption=caption)
        return self.publish_media(container["id"])

    def publish_carousel(self, image_urls, caption):
        child_ids = []
        for image_url in image_urls[:10]:
            container = self.create_media(image_url=image_url, is_carousel_item="true")
            child_ids.append(container["id"])
        container = self.create_media(media_type="CAROUSEL", children=",".join(child_ids), caption=caption)
        return self.publish_media(container["id"])

    def publish_story(self, image_url):
        container = self.create_media(media_type="STORIES", image_url=image_url)
        return self.publish_media(container["id"])

    def publish_reel(self, video_url, caption):
        container = self.create_media(media_type="REELS", video_url=video_url, caption=caption)
        return self.publish_media(container["id"])

    def user_media(self, fields=None, limit=25):
        fields = fields or (
            "id,caption,comments_count,like_count,media_product_type,"
            "media_type,permalink,timestamp"
        )
        return self._get(f"{self.ig_user_id}/media", {"fields": fields, "limit": str(limit)})

    def media_insights(self, media_id, metrics):
        metric_value = ",".join(metrics)
        return self._get(f"{media_id}/insights", {"metric": metric_value})

    def media_comments(self, media_id, limit=50):
        fields = "id,text,username,timestamp,like_count"
        return self._get(f"{media_id}/comments", {"fields": fields, "limit": str(limit)})


def public_url_for(config, local_path):
    base = config.get("public_base_url", "").rstrip("/")
    if not base:
        return ""
    return f"{base}/media/{local_path.name}"
