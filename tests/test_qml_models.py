from app.qml_ui.models import OperationListModel


def test_keyed_qml_model_updates_stable_rows_without_resetting_identity():
    model = OperationListModel()
    model.sync(
        [
            {"operationId": "op-a", "status": "running", "command": "one"},
            {"operationId": "op-b", "status": "succeeded", "command": "two"},
        ]
    )

    assert model.rowCount() == 2
    assert model.find("op-a") == 0

    model.sync(
        [
            {"operationId": "op-a", "status": "succeeded", "command": "one"},
            {"operationId": "op-b", "status": "succeeded", "command": "two"},
        ]
    )

    assert model.find("op-a") == 0
    assert model.get(0)["status"] == "succeeded"


def test_keyed_qml_model_handles_stream_prepend_and_filter_reset():
    model = OperationListModel()
    model.sync(
        [
            {"operationId": "op-b", "status": "succeeded"},
            {"operationId": "op-c", "status": "failed"},
        ]
    )
    model.sync(
        [
            {"operationId": "op-a", "status": "running"},
            {"operationId": "op-b", "status": "succeeded"},
            {"operationId": "op-c", "status": "failed"},
        ]
    )

    assert [row["operationId"] for row in model.rows()] == ["op-a", "op-b", "op-c"]

    model.sync([{"operationId": "op-c", "status": "failed"}])
    assert model.rowCount() == 1
    assert model.get(0)["operationId"] == "op-c"
