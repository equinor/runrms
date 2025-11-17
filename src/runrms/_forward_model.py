from ert import (  # type: ignore
    ForwardModelStepDocumentation,
    ForwardModelStepJSON,
    ForwardModelStepPlugin,
    ForwardModelStepValidationError,
    ForwardModelStepWarning,
    plugin,
)

from runrms.config.fm_config import (
    ForwardModelConfig,
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
        ok, err = ForwardModelConfig._pre_experiment_validation()
        if not ok:
            raise ForwardModelStepValidationError(f"ForwardModelConfig: {err}")

        if "<RMS_PYTHONPATH>" in self.private_args:
            ForwardModelStepWarning.warn(
                "Remove unused option <RMS_PYTHONPATH> from your RMS step "
                "configuration. It has no effect."
            )
        if "<RMS_PATH_PREFIX>" in self.private_args:
            ForwardModelStepWarning.warn(
                "Remove unused option <RMS_PATH_PREFIX> from your RMS step "
                "configuration. It has no effect."
            )

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
def installable_forward_model_steps() -> list[ForwardModelStepPlugin]:
    return [Rms]
