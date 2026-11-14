"""List every journey extract in TfL's public cycling-data S3 bucket."""
import re, sys, urllib.parse
import requests

BUCKET = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"

def list_usage_files(prefix="usage-stats/"):
    rows, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        r = requests.get(BUCKET, params=params, timeout=60)
        r.raise_for_status()
        for block in re.findall(r"<Contents>(.*?)</Contents>", r.text, re.S):
            key = re.search(r"<Key>(.*?)</Key>", block).group(1)
            size = int(re.search(r"<Size>(\d+)</Size>", block).group(1))
            mod = re.search(r"<LastModified>(.*?)</LastModified>", block).group(1)
            rows.append((key, size, mod))
        m = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", r.text)
        if not m:
            return rows
        token = m.group(1)

if __name__ == "__main__":
    for k, s, m in list_usage_files():
        print(k, s, m, sep="\t")
