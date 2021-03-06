#!/usr/bin/env python
"""Tree manipulation script."""
import logging
import os

from scriptworker_client.aio import retry_async
from scriptworker_client.client import sync_main
from treescript.exceptions import CheckoutError, PushError, TreeScriptError
from treescript.mercurial import (
    log_mercurial_version,
    validate_robustcheckout_works,
    checkout_repo,
    do_tagging,
    log_outgoing,
    strip_outgoing,
    push,
)
from treescript.task import task_action_types, is_dry_run
from treescript.versionmanip import bump_version
from treescript.l10n import l10n_bump

log = logging.getLogger(__name__)


async def do_actions(config, task, actions, repo_path):
    """Perform the set of actions that treescript can perform.

    The actions happen in order, tagging, ver bump, then push

    Args:
        config (dict): the running config
        task (dict): the running task
        actions (list): the actions to perform
        repo_path (str): the source directory to use.
        attempts (int, optional): the number of attempts to perform,
            retrying on error.

    """
    await checkout_repo(config, task, repo_path)
    changes = []
    for action in actions:
        if action in ["tagging", "tag"]:
            changes.append(await do_tagging(config, task, repo_path))
        elif "version_bump" == action:
            changes.append(await bump_version(config, task, repo_path))
        elif "l10n_bump" == action:
            changes.append(await l10n_bump(config, task, repo_path))
        elif "push" == action:
            pass  # handled after log_outgoing
        else:
            raise NotImplementedError("Unexpected action")
    await log_outgoing(config, task, repo_path)
    if is_dry_run(task):
        log.info("Not pushing changes, dry_run was forced")
    elif "push" in actions:
        if any(changes):
            await push(config, task, repo_path)
        else:
            log.info("No changes; skipping push.")
    else:
        log.info("Not pushing changes, lacking scopes")
    await strip_outgoing(config, task, repo_path)


# async_main {{{1
async def async_main(config, task):
    """Run all the vcs things.

    Args:
        config (dict): the running config.
        task (dict): the running task.

    """
    work_dir = config["work_dir"]
    repo_path = os.path.join(work_dir, "src")
    actions_to_perform = task_action_types(config, task)
    await log_mercurial_version(config)
    if not await validate_robustcheckout_works(config):
        raise TreeScriptError("Robustcheckout can't run on our version of hg, aborting")
    await retry_async(
        do_actions,
        args=(config, task, actions_to_perform, repo_path),
        retry_exceptions=(CheckoutError, PushError),
    )
    log.info("Done!")


# config {{{1
def get_default_config(base_dir=None):
    """Create the default config to work from.

    Args:
        base_dir (str, optional): the directory above the `work_dir` and `artifact_dir`.
            If None, use `..`  Defaults to None.

    Returns:
        dict: the default configuration dict.

    """
    base_dir = base_dir or os.path.dirname(os.getcwd())
    default_config = {
        "work_dir": os.path.join(base_dir, "work_dir"),
        "hg": "hg",
        "schema_file": os.path.join(
            os.path.dirname(__file__), "data", "treescript_task_schema.json"
        ),
    }
    return default_config


def main():
    """Start treescript."""
    return sync_main(async_main, default_config=get_default_config())


__name__ == "__main__" and main()
