# Images Folder

Quick rundown of the container image definitions in this directory.

## `Containerfile.ci`

- Base image: `pipeline:claude-ai-helpers` (Injected during building in prow)
- Purpose: CI runtime image for edge-tooling workflows.
- Adds:
  - `gh-token` binary (injected during CI build)
  - full repository contents at `/opt/app-root/src/edge-tooling`
- Sets `WORKDIR` to the copied repo path.

## `Containerfile.tooling`

- Base image: `root` ([root](https://github.com/eggfoobar/release/blob/7575a28879c0c7b624daad64799aa85dd6d783bc/ci-operator/config/openshift-eng/edge-tooling/openshift-eng-edge-tooling-main.yaml#L37) is the `build_root` image defined in prow, [example](https://github.com/eggfoobar/release/blob/7575a28879c0c7b624daad64799aa85dd6d783bc/ci-operator/config/openshift-eng/edge-tooling/openshift-eng-edge-tooling-main.yaml#L10-L14))
- Purpose: general tooling image.
- Uses `images/install_tools.sh` functions to install:
  - `gh-token`
  - Google Cloud CLI (`gcloud`)
- Removes temporary installer script after setup.

## `Containerfile.markdownlint`

- Base image: `root` ([root](https://github.com/eggfoobar/release/blob/7575a28879c0c7b624daad64799aa85dd6d783bc/ci-operator/config/openshift-eng/edge-tooling/openshift-eng-edge-tooling-main.yaml#L37) is the `build_root` image defined in prow, [example](https://github.com/eggfoobar/release/blob/7575a28879c0c7b624daad64799aa85dd6d783bc/ci-operator/config/openshift-eng/edge-tooling/openshift-eng-edge-tooling-main.yaml#L10-L14))
- Purpose: markdown linting image kept separate from general tooling.
- Installs Node.js 22 via `dnf module`.
- Uses `images/install_tools.sh` functions to install:
  - `markdownlint`
  - `markdownlint-cli2`
  - json / pretty / junit formatters
- Runs cleanup to remove package manager caches and temp install artifacts.

## `install_tools.sh`

Shared install functions used by the containerfiles:

- `install_gh_token`
- `install_google_cloud_cli`
- `install_markdown_tools`
- `cleanup_install_artifacts`

Key env vars:

| Variable | What it controls |
| --- | --- |
| `GH_TOKEN_VER` | Version of `gh-token` binary to download. |
| `GH_TOKEN_SHA` | Expected SHA256 checksum used to verify the downloaded `gh-token` binary. |
| `GH_TOKEN_RETRY_COUNT` | Number of retry attempts for downloading `gh-token` when the request fails. |
| `GOOGLE_CLOUD_REPO_URL` | Yum repository URL used to install Google Cloud CLI packages. |
| `MARKDOWNLINT_VERSION` | Version of the `markdownlint` npm package installed in the markdownlint image. |
| `MARKDOWNLINT_CLI2_VERSION` | Version of the `markdownlint-cli2` npm package installed in the markdownlint image. |
