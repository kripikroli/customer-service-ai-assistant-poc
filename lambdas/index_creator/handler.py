"""Custom resource handler to create OpenSearch Serverless vector index."""

import json
import urllib.request
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


def handler(event, context):
    props = event["ResourceProperties"]
    endpoint = props["CollectionEndpoint"]
    index_name = props["IndexName"]
    region = props["Region"]

    status = "SUCCESS"
    reason = ""
    try:
        if event["RequestType"] in ("Create", "Update"):
            creds = boto3.Session().get_credentials().get_frozen_credentials()
            auth = AWS4Auth(creds.access_key, creds.secret_key, region, "aoss", session_token=creds.token)
            host = endpoint.replace("https://", "")
            client = OpenSearch(
                hosts=[{"host": host, "port": 443}],
                http_auth=auth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
            )
            if not client.indices.exists(index=index_name):
                client.indices.create(
                    index=index_name,
                    body={
                        "settings": {"index.knn": True},
                        "mappings": {
                            "properties": {
                                "vector": {
                                    "type": "knn_vector",
                                    "dimension": 1024,
                                    "method": {"engine": "faiss", "name": "hnsw"},
                                },
                                "text": {"type": "text"},
                                "metadata": {"type": "text"},
                            }
                        },
                    },
                )
    except Exception as e:
        status = "FAILED"
        reason = str(e)

    body = json.dumps(
        {
            "Status": status,
            "Reason": reason,
            "PhysicalResourceId": f"{endpoint}/{index_name}",
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
        }
    )
    urllib.request.urlopen(urllib.request.Request(event["ResponseURL"], data=body.encode(), method="PUT"))
