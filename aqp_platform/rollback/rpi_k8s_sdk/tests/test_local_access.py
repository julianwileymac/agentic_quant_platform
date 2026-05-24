"""Unit coverage for local access helpers."""

from __future__ import annotations

from pathlib import Path


def test_write_env_file(tmp_path: Path):
    from rpi_k8s_sdk import LocalAccessSettings, write_env_file

    target = write_env_file(tmp_path / "lab.env", LocalAccessSettings(kube_context="rpi"))

    text = target.read_text(encoding="utf-8")
    assert "RPI_K8S_CONTEXT=rpi" in text
    assert "MINIO_ENDPOINT=http://s3.local" in text


def test_minio_client_uses_injected_client():
    from rpi_k8s_sdk import MinioClient

    class FakeS3:
        def __init__(self):
            self.buckets = set()
            self.objects = {}

        def list_buckets(self):
            return {"Buckets": [{"Name": name} for name in sorted(self.buckets)]}

        def head_bucket(self, Bucket):
            if Bucket not in self.buckets:
                raise RuntimeError("missing bucket")

        def create_bucket(self, Bucket):
            self.buckets.add(Bucket)

        def put_object(self, **kwargs):
            self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]
            return {"ETag": "fake"}

        def get_object(self, Bucket, Key):
            class Body:
                def __init__(self, payload):
                    self.payload = payload

                def read(self):
                    return self.payload

            return {"Body": Body(self.objects[(Bucket, Key)])}

    fake = FakeS3()
    client = MinioClient(client=fake)
    obj = client.put_bytes("pipeline-raw", "sample.json", b"{}")

    assert obj.bucket == "pipeline-raw"
    assert client.download_bytes("pipeline-raw", "sample.json") == b"{}"
    assert client.health()["buckets"] == ["pipeline-raw"]


def test_datahub_recipes_are_local_sinked():
    from rpi_k8s_sdk import DataHubClient, LocalAccessSettings

    client = DataHubClient(LocalAccessSettings(datahub_gms_url="http://127.0.0.1:8080"))
    recipe = client.mlflow_recipe().as_dict()

    assert recipe["source"]["type"] == "mlflow"
    assert recipe["sink"]["config"]["server"] == "http://127.0.0.1:8080"


def test_iceberg_config_points_to_rest_catalog():
    from rpi_k8s_sdk import IcebergClient

    config = IcebergClient().config()

    assert config.options["type"] == "rest"
    assert config.options["uri"].endswith("/iceberg")
    assert config.options["s3.path-style-access"] == "true"


def test_pipeline_client_parses_created_workflow():
    from rpi_k8s_sdk import ArgoPipelineClient

    class FakeCustomApi:
        def create_namespaced_custom_object(self, **kwargs):
            return {"metadata": {"name": "raw-ingest-sample-abc"}, "status": {"phase": "Running"}}

    run = ArgoPipelineClient(custom_api=FakeCustomApi()).raw_ingest(
        source_name="sample",
        source_uri="https://example.com/data.json",
    )

    assert run.name == "raw-ingest-sample-abc"
    assert run.status == "Running"
    assert run.parameters["target_bucket"] == "pipeline-raw"
    assert run.argo_ui_path == "/workflows/mlops/raw-ingest-sample-abc"
