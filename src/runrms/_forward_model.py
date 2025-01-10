from __future__ import annotations

from ert import (  # type: ignore
    ForwardModelStepDocumentation,
    ForwardModelStepJSON,
    ForwardModelStepPlugin,
    ForwardModelStepValidationError,
    plugin,
)

from runrms.config.fm_rms_config import (
    FMRMSConfig,
    description,
    examples,
)


class Rms(ForwardModelStepPlugin):  # type: ignore
    def __init__(self) -> None:
        super().__init__(
            name="RMS",
            command=[
                "runrms",
                "<RMS_PROJECT>",
                "--batch",
                "<RMS_WORKFLOW>",
                "--iens",
                "<IENS>",
                "--run-path",
                "<RMS_RUNPATH>",
                "--target-file",
                "<RMS_TARGET_FILE>",
                "--import-path",
                "<RMS_IMPORT_PATH>",
                "-v",
                "<RMS_VERSION>",
                "--export-path",
                "<RMS_EXPORT_PATH>",
                "<RMS_OPTS>",
            ],
            default_mapping={
                "<RMS_IMPORT_PATH>": "./",
                "<RMS_EXPORT_PATH>": "./",
                "<RMS_RUNPATH>": "rms/model",
                "<RMS_OPTS>": "",
            },
            target_file="<RMS_TARGET_FILE>",
        )

    def validate_pre_realization_run(
        self, fm_step_json: ForwardModelStepJSON
    ) -> ForwardModelStepJSON:
        return fm_step_json

    def validate_pre_experiment(self, fm_step_json: ForwardModelStepJSON) -> None:
        ok, err = FMRMSConfig._pre_experiment_validation()
        if not ok:
            raise ForwardModelStepValidationError(f"FMRMSConfig: {err}")

    @staticmethod
    def documentation() -> ForwardModelStepDocumentation | None:
        return ForwardModelStepDocumentation(
            category="modelling.reservoir",
            source_package="runrms",
            source_function_name="Rms",
            description=description,
            examples=examples,
        )


@plugin(name="runrms")  # type: ignore
def forward_model_configuration() -> dict[str, dict[str, str]]:
    """These exist for backward compatibility but have no effect."""
    return {
        Rms().name: {
            "RMS_PYTHONPATH": "<RMS_PYTHONPATH>",
            "RMS_PATH_PREFIX": "<RMS_PATH_PREFIX>",
        }
    }


@plugin(name="runrms")  # type: ignore
def installable_forward_model_steps() -> list[ForwardModelStepPlugin]:
    return [Rms]
