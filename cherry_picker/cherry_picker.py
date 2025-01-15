#!/usr/bin/env python3

from __future__ import annotations

import collections
import enum
import functools
import os
import re
import subprocess
import sys
import webbrowser

import click
import requests
import stamina
from gidgethub import sansio

from . import __version__

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CREATE_PR_URL_TEMPLATE = (
    "https://api.github.com/repos/{config[team]}/{config[repo]}/pulls"
)
DEFAULT_CONFIG = collections.ChainMap(
    {
        "team": "python",
        "repo": "cpython",
        "check_sha": "7f777ed95a19224294949e1b4ce56bbffcb1fe9f",
        "fix_commit_msg": True,
        "default_branch": "main",
        "require_version_in_branch_name": True,
        "draft_pr": False,
    }
)


WORKFLOW_STATES = enum.Enum(
    "WORKFLOW_STATES",
    """
    FETCHING_UPSTREAM
    FETCHED_UPSTREAM

    CHECKING_OUT_DEFAULT_BRANCH
    CHECKED_OUT_DEFAULT_BRANCH

    CHECKING_OUT_PREVIOUS_BRANCH
    CHECKED_OUT_PREVIOUS_BRANCH

    PUSHING_TO_REMOTE
    PUSHED_TO_REMOTE
    PUSHING_TO_REMOTE_FAILED

    PR_CREATING
    PR_CREATING_FAILED
    PR_OPENING

    REMOVING_BACKPORT_BRANCH
    REMOVING_BACKPORT_BRANCH_FAILED
    REMOVED_BACKPORT_BRANCH

    BACKPORT_STARTING
    BACKPORT_LOOPING
    BACKPORT_LOOP_START
    BACKPORT_LOOP_END

    ABORTING
    ABORTED
    ABORTING_FAILED

    CONTINUATION_STARTED
    BACKPORTING_CONTINUATION_SUCCEED
    CONTINUATION_FAILED

    BACKPORT_PAUSED

    UNSET
    """,
)


class BranchCheckoutException(Exception):
    def __init__(self, branch_name):
        self.branch_name = branch_name
        super().__init__(f"Error checking out the branch {branch_name!r}.")


class CherryPickException(Exception):
    pass


class InvalidRepoException(Exception):
    pass


class GitHubException(Exception):
    pass


class CherryPicker:
    ALLOWED_STATES = WORKFLOW_STATES.BACKPORT_PAUSED, WORKFLOW_STATES.UNSET
    """The list of states expected at the start of the app."""

    def __init__(
        self,
        pr_remote,
        commit_sha1,
        branches,
        *,
        upstream_remote=None,
        dry_run=False,
        push=True,
        prefix_commit=True,
        config=DEFAULT_CONFIG,
        chosen_config_path=None,
        auto_pr=True,
    ):
        self.chosen_config_path = chosen_config_path
        """The config reference used in the current runtime.

        It starts with a Git revision specifier, followed by a colon
        and a path relative to the repo root.
        """

        self.config = config
        self.check_repo()  # may raise InvalidRepoException

        """The runtime state loaded from the config.

        Used to verify that we resume the process from the valid
        previous state.
        """

        if dry_run:
            click.echo("Dry run requested, listing expected command sequence")

        self.pr_remote = pr_remote
        self.upstream_remote = upstream_remote
        self.commit_sha1 = commit_sha1
        self.branches = branches
        self.dry_run = dry_run
        self.push = push
        self.auto_pr = auto_pr
        self.prefix_commit = prefix_commit

        # the cached calculated value of self.upstream property
        self._upstream = None

        # This is set to the PR number when cherry-picker successfully
        # creates a PR through API.
        self.pr_number = None

    def set_paused_state(self):
        """Save paused progress state into Git config."""
        if self.chosen_config_path is not None:
            save_cfg_vals_to_git_cfg(config_path=self.chosen_config_path)
        set_state(WORKFLOW_STATES.BACKPORT_PAUSED)

    def remember_previous_branch(self):
        """Save the current branch into Git config, to be used later."""
        current_branch = get_current_branch()
        save_cfg_vals_to_git_cfg(previous_branch=current_branch)

    @property
    def upstream(self):
        """Get the remote name to use for upstream branches

        Uses the remote passed to `--upstream-remote`.
        If this flag wasn't passed, it uses "upstream" if it exists or "origin"
        otherwise.
        """
        # the cached calculated value of the property
        if self._upstream is not None:
            return self._upstream

        cmd = ["git", "remote", "get-url", "upstream"]
        if self.upstream_remote is not None:
            cmd[-1] = self.upstream_remote

        try:
            self.run_cmd(cmd, required_real_result=True)
        except subprocess.CalledProcessError:
            if self.upstream_remote is not None:
                raise ValueError(f"There is no remote with name {cmd[-1]!r}.")
            cmd[-1] = "origin"
            try:
                self.run_cmd(cmd)
            except subprocess.CalledProcessError:
                raise ValueError(
                    "There are no remotes with name 'upstream' or 'origin'."
                )

        self._upstream = cmd[-1]
        return self._upstream

    @property
    def sorted_branches(self):
        """Return the branches to cherry-pick to, sorted by version."""
        return sorted(
            self.branches, key=functools.partial(compute_version_sort_key, self.config)
        )

    @property
    def username(self):
        cmd = ["git", "config", "--get", f"remote.{self.pr_remote}.url"]
        result = self.run_cmd(cmd, required_real_result=True).strip()
        # implicit ssh URIs use : to separate host from user, others just use /
        username = result.replace(":", "/").rstrip("/").split("/")[-2]
        return username

    def get_cherry_pick_branch(self, maint_branch):
        return f"backport-{self.commit_sha1[:7]}-{maint_branch}"

    def get_pr_url(self, base_branch, head_branch):
        return (
            f"https://github.com/{self.config['team']}/{self.config['repo']}"
            f"/compare/{base_branch}...{self.username}:{head_branch}?expand=1"
        )

    def fetch_upstream(self):
        """git fetch <upstream>"""
        set_state(WORKFLOW_STATES.FETCHING_UPSTREAM)
        cmd = ["git", "fetch", self.upstream, "--no-tags"]
        self.run_cmd(cmd)
        set_state(WORKFLOW_STATES.FETCHED_UPSTREAM)

    def run_cmd(self, cmd, required_real_result=False):
        assert not isinstance(cmd, str)
        if not required_real_result and self.dry_run:
            click.echo(f"  dry-run: {' '.join(cmd)}")
            return
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return output.decode("utf-8")

    def checkout_branch(self, branch_name, *, create_branch=False):
        """git checkout [-b] <branch_name>"""
        if create_branch:
            checked_out_branch = self.get_cherry_pick_branch(branch_name)
            cmd = [
                "git",
                "checkout",
                "-b",
                checked_out_branch,
                f"{self.upstream}/{branch_name}",
            ]
        else:
            checked_out_branch = branch_name
            cmd = ["git", "checkout", branch_name]
        try:
            self.run_cmd(cmd)
        except subprocess.CalledProcessError as err:
            click.echo(f"Error checking out the branch {checked_out_branch!r}.")
            click.echo(err.output)
            raise BranchCheckoutException(checked_out_branch)
        if create_branch:
            self.unset_upstream(checked_out_branch)

    def get_commit_message(self, commit_sha):
        """
        Return the commit message for the current commit hash,
        replace #<PRID> with GH-<PRID>
        """
        cmd = ["git", "show", "-s", "--format=%B", commit_sha]
        try:
            message = self.run_cmd(cmd, required_real_result=True).strip()
        except subprocess.CalledProcessError as err:
            click.echo(f"Error getting commit message for {commit_sha}")
            click.echo(err.output)
            raise CherryPickException(f"Error getting commit message for {commit_sha}")
        if self.config["fix_commit_msg"]:
            # Only replace "#" with "GH-" with the following conditions:
            # * "#" is separated from the previous word
            # * "#" is followed by at least 5-digit number that
            #   does not start with 0
            # * the number is separated from the following word
            return re.sub(r"\B#(?=[1-9][0-9]{4,}\b)", "GH-", message)
        else:
            return message

    def checkout_default_branch(self):
        """git checkout default branch"""
        set_state(WORKFLOW_STATES.CHECKING_OUT_DEFAULT_BRANCH)

        self.checkout_branch(self.config["default_branch"])

        set_state(WORKFLOW_STATES.CHECKED_OUT_DEFAULT_BRANCH)

    def checkout_previous_branch(self):
        """git checkout previous branch"""
        set_state(WORKFLOW_STATES.CHECKING_OUT_PREVIOUS_BRANCH)

        previous_branch = load_val_from_git_cfg("previous_branch")
        if previous_branch is None:
            self.checkout_default_branch()
            return

        self.checkout_branch(previous_branch)

        set_state(WORKFLOW_STATES.CHECKED_OUT_PREVIOUS_BRANCH)

    def status(self):
        """
        git status
        :return:
        """
        cmd = ["git", "status"]
        return self.run_cmd(cmd)

    def cherry_pick(self):
        """git cherry-pick -x <commit_sha1>"""
        cmd = ["git", "cherry-pick", "-x", self.commit_sha1]
        try:
            click.echo(self.run_cmd(cmd))
        except subprocess.CalledProcessError as err:
            click.echo(f"Error cherry-pick {self.commit_sha1}.")
            click.echo(err.output)
            raise CherryPickException(f"Error cherry-pick {self.commit_sha1}.")

    def get_exit_message(self, branch):
        return f"""
Failed to cherry-pick {self.commit_sha1} into {branch} \u2639
... Stopping here.

To continue and resolve the conflict:
    $ cherry_picker --status  # to find out which files need attention
    # Fix the conflict
    $ cherry_picker --status  # should now say 'all conflict fixed'
    $ cherry_picker --continue

To abort the cherry-pick and cleanup:
    $ cherry_picker --abort
"""

    def get_updated_commit_message(self, cherry_pick_branch):
        """
        Get updated commit message for the cherry-picked commit.
        """
        # Get the original commit message and prefix it with the branch name
        # if that's enabled.
        updated_commit_message = self.get_commit_message(self.commit_sha1)
        if self.prefix_commit:
            updated_commit_message = remove_commit_prefix(updated_commit_message)
            base_branch = get_base_branch(cherry_pick_branch, config=self.config)
            updated_commit_message = f"[{base_branch}] {updated_commit_message}"

        # Add '(cherry picked from commit ...)' to the message
        # and add new Co-authored-by trailer if necessary.
        cherry_pick_information = f"(cherry picked from commit {self.commit_sha1})\n:"
        # Here, we're inserting new Co-authored-by trailer and we *somewhat*
        # abuse interpret-trailers by also adding cherry_pick_information which
        # is not an actual trailer.
        # `--where start` makes it so we insert new trailers *before* the existing
        # trailers so cherry-pick information gets added before any of the trailers
        # which prevents us from breaking the trailers.
        cmd = [
            "git",
            "interpret-trailers",
            "--where",
            "start",
            "--trailer",
            f"Co-authored-by: {get_author_info_from_short_sha(self.commit_sha1)}",
            "--trailer",
            cherry_pick_information,
        ]
        output = subprocess.check_output(cmd, input=updated_commit_message.encode())
        # Replace the right most-occurence of the "cherry picked from commit" string.
        #
        # This needs to be done because `git interpret-trailers` required us to add `:`
        # to `cherry_pick_information` when we don't actually want it.
        before, after = (
            output.strip().decode().rsplit(f"\n{cherry_pick_information}", 1)
        )
        if not before.endswith("\n"):
            # ensure that we still have a newline between cherry pick information
            # and commit headline
            cherry_pick_information = f"\n{cherry_pick_information}"
        updated_commit_message = cherry_pick_information[:-1].join((before, after))

        return updated_commit_message

    def amend_commit_message(self, cherry_pick_branch):
        """Prefix the commit message with (X.Y)"""

        updated_commit_message = self.get_updated_commit_message(cherry_pick_branch)
        if self.dry_run:
            click.echo(f"  dry-run: git commit --amend -m '{updated_commit_message}'")
        else:
            cmd = ["git", "commit", "--amend", "-m", updated_commit_message]
            try:
                self.run_cmd(cmd)
            except subprocess.CalledProcessError as cpe:
                click.echo("Failed to amend the commit message \u2639")
                click.echo(cpe.output)
        return updated_commit_message

    def pause_after_committing(self, cherry_pick_branch):
        click.echo(
            f"""
Finished cherry-pick {self.commit_sha1} into {cherry_pick_branch} \U0001F600
--no-push option used.
... Stopping here.
To continue and push the changes:
$ cherry_picker --continue

To abort the cherry-pick and cleanup:
$ cherry_picker --abort
"""
        )
        self.set_paused_state()

    def push_to_remote(self, base_branch, head_branch, commit_message=""):
        """git push <origin> <branchname>"""
        set_state(WORKFLOW_STATES.PUSHING_TO_REMOTE)

        cmd = ["git", "push"]
        if head_branch.startswith("backport-"):
            # Overwrite potential stale backport branches with extreme prejudice.
            cmd.append("--force-with-lease")
        cmd.append(self.pr_remote)
        if not self.is_mirror():
            cmd.append(f"{head_branch}:{head_branch}")
        try:
            self.run_cmd(cmd)
            set_state(WORKFLOW_STATES.PUSHED_TO_REMOTE)
        except subprocess.CalledProcessError as cpe:
            click.echo(f"Failed to push to {self.pr_remote} \u2639")
            click.echo(cpe.output)
            set_state(WORKFLOW_STATES.PUSHING_TO_REMOTE_FAILED)
        else:
            if not self.auto_pr:
                return
            gh_auth = os.getenv("GH_AUTH")
            if gh_auth:
                set_state(WORKFLOW_STATES.PR_CREATING)
                try:
                    self.create_gh_pr(
                        base_branch,
                        head_branch,
                        commit_message=commit_message,
                        gh_auth=gh_auth,
                    )
                except GitHubException:
                    set_state(WORKFLOW_STATES.PR_CREATING_FAILED)
                    raise
            else:
                set_state(WORKFLOW_STATES.PR_OPENING)
                self.open_pr(self.get_pr_url(base_branch, head_branch))

    @stamina.retry(on=GitHubException, timeout=120)
    def create_gh_pr(self, base_branch, head_branch, *, commit_message, gh_auth):
        """
        Create PR in GitHub
        """
        request_headers = sansio.create_headers(self.username, oauth_token=gh_auth)
        title, body = normalize_commit_message(commit_message)
        if not self.prefix_commit:
            title = remove_commit_prefix(title)
            title = f"[{base_branch}] {title}"
        data = {
            "title": title,
            "body": body,
            "head": f"{self.username}:{head_branch}",
            "base": base_branch,
            "maintainer_can_modify": True,
            "draft": self.config["draft_pr"],
        }
        url = CREATE_PR_URL_TEMPLATE.format(config=self.config)
        try:
            response = requests.post(
                url, headers=request_headers, json=data, timeout=30
            )
        except requests.exceptions.RequestException as req_exc:
            raise GitHubException(f"Creating PR on GitHub failed: {req_exc}")
        else:
            sc = response.status_code
            txt = response.text
            if sc != requests.codes.created:
                raise GitHubException(
                    f"Unexpected response ({sc}) when creating PR on GitHub: {txt}"
                )
        response_data = response.json()
        click.echo(f"Backport PR created at {response_data['html_url']}")
        self.pr_number = response_data["number"]

    def open_pr(self, url):
        """
        open url in the web browser
        """
        if self.dry_run:
            click.echo(f"  dry-run: Create new PR: {url}")
        else:
            click.echo("Backport PR URL:")
            click.echo(url)
            webbrowser.open_new_tab(url)

    def delete_branch(self, branch):
        cmd = ["git", "branch", "-D", branch]
        return self.run_cmd(cmd)

    def cleanup_branch(self, branch):
        """Remove the temporary backport branch.

        Switch to the default branch before that.
        """
        set_state(WORKFLOW_STATES.REMOVING_BACKPORT_BRANCH)
        try:
            self.checkout_previous_branch()
        except BranchCheckoutException:
            click.echo(f"branch {branch} NOT deleted.")
            set_state(WORKFLOW_STATES.REMOVING_BACKPORT_BRANCH_FAILED)
            return
        try:
            self.delete_branch(branch)
        except subprocess.CalledProcessError:
            click.echo(f"branch {branch} NOT deleted.")
            set_state(WORKFLOW_STATES.REMOVING_BACKPORT_BRANCH_FAILED)
        else:
            click.echo(f"branch {branch} has been deleted.")
            set_state(WORKFLOW_STATES.REMOVED_BACKPORT_BRANCH)

    def unset_upstream(self, branch):
        cmd = ["git", "branch", "--unset-upstream", branch]
        try:
            return self.run_cmd(cmd)
        except subprocess.CalledProcessError as cpe:
            click.echo(cpe.output)

    def backport(self):
        if not self.branches:
            raise click.UsageError("At least one branch must be specified.")
        set_state(WORKFLOW_STATES.BACKPORT_STARTING)
        self.fetch_upstream()
        self.remember_previous_branch()

        set_state(WORKFLOW_STATES.BACKPORT_LOOPING)
        for maint_branch in self.sorted_branches:
            set_state(WORKFLOW_STATES.BACKPORT_LOOP_START)
            click.echo(f"Now backporting '{self.commit_sha1}' into '{maint_branch}'")

            cherry_pick_branch = self.get_cherry_pick_branch(maint_branch)
            try:
                self.checkout_branch(maint_branch, create_branch=True)
            except BranchCheckoutException:
                self.checkout_default_branch()
                reset_stored_config_ref()
                reset_state()
                raise
            commit_message = ""
            try:
                self.cherry_pick()
                commit_message = self.amend_commit_message(cherry_pick_branch)
            except subprocess.CalledProcessError as cpe:
                click.echo(cpe.output)
                click.echo(self.get_exit_message(maint_branch))
            except CherryPickException:
                click.echo(self.get_exit_message(maint_branch))
                self.set_paused_state()
                raise
            else:
                if self.push:
                    try:
                        self.push_to_remote(
                            maint_branch, cherry_pick_branch, commit_message
                        )
                    except GitHubException:
                        click.echo(self.get_exit_message(maint_branch))
                        self.set_paused_state()
                        raise
                    if not self.is_mirror():
                        self.cleanup_branch(cherry_pick_branch)
                else:
                    self.pause_after_committing(cherry_pick_branch)
                    return  # to preserve the correct state
            set_state(WORKFLOW_STATES.BACKPORT_LOOP_END)
        reset_stored_previous_branch()
        reset_state()

    def abort_cherry_pick(self):
        """
        run `git cherry-pick --abort` and then clean up the branch
        """
        state = self.get_state_and_verify()
        if state != WORKFLOW_STATES.BACKPORT_PAUSED:
            raise ValueError(
                f"One can only abort a paused process. "
                f"Current state: {state}. "
                f"Expected state: {WORKFLOW_STATES.BACKPORT_PAUSED}"
            )

        try:
            validate_sha("CHERRY_PICK_HEAD")
        except ValueError:
            pass
        else:
            cmd = ["git", "cherry-pick", "--abort"]
            try:
                set_state(WORKFLOW_STATES.ABORTING)
                click.echo(self.run_cmd(cmd))
                set_state(WORKFLOW_STATES.ABORTED)
            except subprocess.CalledProcessError as cpe:
                click.echo(cpe.output)
                set_state(WORKFLOW_STATES.ABORTING_FAILED)
        # only delete backport branch created by cherry_picker.py
        if get_current_branch().startswith("backport-"):
            self.cleanup_branch(get_current_branch())

        reset_stored_previous_branch()
        reset_stored_config_ref()
        reset_state()

    def continue_cherry_pick(self):
        """
        git push origin <current_branch>
        open the PR
        clean up branch
        """
        state = self.get_state_and_verify()
        if state != WORKFLOW_STATES.BACKPORT_PAUSED:
            raise ValueError(
                "One can only continue a paused process. "
                f"Current state: {state}. "
                f"Expected state: {WORKFLOW_STATES.BACKPORT_PAUSED}"
            )

        cherry_pick_branch = get_current_branch()
        if cherry_pick_branch.startswith("backport-"):
            set_state(WORKFLOW_STATES.CONTINUATION_STARTED)
            # amend the commit message, prefix with [X.Y]
            base = get_base_branch(cherry_pick_branch, config=self.config)
            short_sha = cherry_pick_branch[
                cherry_pick_branch.index("-") + 1 : cherry_pick_branch.index(base) - 1
            ]
            self.commit_sha1 = get_full_sha_from_short(short_sha)

            commits = get_commits_from_backport_branch(base)
            if len(commits) == 1:
                commit_message = self.amend_commit_message(cherry_pick_branch)
            else:
                commit_message = self.get_updated_commit_message(cherry_pick_branch)
                if self.dry_run:
                    click.echo(
                        f"  dry-run: git commit -a -m '{commit_message}' --allow-empty"
                    )
                else:
                    cmd = [
                        "git",
                        "commit",
                        "-a",
                        "-m",
                        commit_message,
                        "--allow-empty",
                    ]
                    self.run_cmd(cmd)

            if self.push:
                self.push_to_remote(base, cherry_pick_branch)

                if not self.is_mirror():
                    self.cleanup_branch(cherry_pick_branch)

                click.echo("\nBackport PR:\n")
                click.echo(commit_message)
                set_state(WORKFLOW_STATES.BACKPORTING_CONTINUATION_SUCCEED)
            else:
                self.pause_after_committing(cherry_pick_branch)
                return  # to preserve the correct state

        else:
            click.echo(
                f"Current branch ({cherry_pick_branch}) is not a backport branch. "
                "Will not continue. \U0001F61B"
            )
            set_state(WORKFLOW_STATES.CONTINUATION_FAILED)

        reset_stored_previous_branch()
        reset_stored_config_ref()
        reset_state()

    def check_repo(self):
        """
        Check that the repository is for the project we're configured to operate on.

        This function performs the check by making sure that the sha specified in the
        config is present in the repository that we're operating on.
        """
        try:
            validate_sha(self.config["check_sha"])
            self.get_state_and_verify()
        except ValueError as ve:
            raise InvalidRepoException(ve.args[0])

    def get_state_and_verify(self):
        """Return the run progress state stored in the Git config.

        Raises ValueError if the retrieved state is not of a form that
                          cherry_picker would have stored in the config.
        """
        try:
            state = get_state()
        except KeyError as ke:

            class state:
                name = str(ke.args[0])

        if state not in self.ALLOWED_STATES:
            raise ValueError(
                f"Run state cherry-picker.state={state.name} in Git config "
                "is not known.\nPerhaps it has been set by a newer "
                "version of cherry-picker. Try upgrading.\n"
                "Valid states are: "
                f'{", ".join(s.name for s in self.ALLOWED_STATES)}. '
                "If this looks suspicious, raise an issue at "
                "https://github.com/python/cherry-picker/issues/new.\n"
                "As the last resort you can reset the runtime state "
                "stored in Git config using the following command: "
                "`git config --local --remove-section cherry-picker`"
            )
        return state

    def is_mirror(self) -> bool:
        """Return True if the current repository was created with --mirror."""

        cmd = ["git", "config", "--local", "--get", "remote.origin.mirror"]
        try:
            out = self.run_cmd(cmd, required_real_result=True)
        except subprocess.CalledProcessError:
            return False
        return out.startswith("true")


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.command(context_settings=CONTEXT_SETTINGS)
@click.version_option(version=__version__)
@click.option(
    "--dry-run", is_flag=True, help="Prints out the commands, but not executed."
)
@click.option(
    "--pr-remote",
    "pr_remote",
    metavar="REMOTE",
    help="git remote to use for PR branches",
    default="origin",
)
@click.option(
    "--upstream-remote",
    "upstream_remote",
    metavar="REMOTE",
    help="git remote to use for upstream branches",
    default=None,
)
@click.option(
    "--abort",
    "abort",
    flag_value=True,
    default=None,
    help="Abort current cherry-pick and clean up branch",
)
@click.option(
    "--continue",
    "abort",
    flag_value=False,
    default=None,
    help="Continue cherry-pick, push, and clean up branch",
)
@click.option(
    "--status",
    "status",
    flag_value=True,
    default=None,
    help="Get the status of cherry-pick",
)
@click.option(
    "--push/--no-push",
    "push",
    is_flag=True,
    default=True,
    help="Changes won't be pushed to remote",
)
@click.option(
    "--auto-pr/--no-auto-pr",
    "auto_pr",
    is_flag=True,
    default=True,
    help=(
        "If auto PR is enabled, cherry-picker will automatically open a PR"
        " through API if GH_AUTH env var is set, or automatically open the PR"
        " creation page in the web browser otherwise."
    ),
)
@click.option(
    "--config-path",
    "config_path",
    metavar="CONFIG-PATH",
    help=(
        "Path to config file, .cherry_picker.toml "
        "from project root by default. You can prepend "
        "a colon-separated Git 'commitish' reference."
    ),
    default=None,
)
@click.argument("commit_sha1", nargs=1, default="")
@click.argument("branches", nargs=-1)
@click.pass_context
def cherry_pick_cli(
    ctx,
    dry_run,
    pr_remote,
    upstream_remote,
    abort,
    status,
    push,
    auto_pr,
    config_path,
    commit_sha1,
    branches,
):
    """cherry-pick COMMIT_SHA1 into target BRANCHES."""

    click.echo("\U0001F40D \U0001F352 \u26CF")

    try:
        chosen_config_path, config = load_config(config_path)
    except ValueError as exc:
        click.echo("You're not inside a Git tree right now! \U0001F645", err=True)
        click.echo(exc, err=True)
        sys.exit(-1)
    try:
        cherry_picker = CherryPicker(
            pr_remote,
            commit_sha1,
            branches,
            upstream_remote=upstream_remote,
            dry_run=dry_run,
            push=push,
            auto_pr=auto_pr,
            config=config,
            chosen_config_path=chosen_config_path,
        )
    except InvalidRepoException as ire:
        click.echo(ire.args[0], err=True)
        sys.exit(-1)
    except ValueError as exc:
        ctx.fail(exc)

    if abort is not None:
        if abort:
            cherry_picker.abort_cherry_pick()
        else:
            cherry_picker.continue_cherry_pick()

    elif status:
        click.echo(cherry_picker.status())
    else:
        try:
            cherry_picker.backport()
        except BranchCheckoutException:
            sys.exit(-1)
        except CherryPickException:
            sys.exit(-1)


def get_base_branch(cherry_pick_branch, *, config):
    """
    return '2.7' from 'backport-sha-2.7'

    raises ValueError if the specified branch name is not of a form that
        cherry_picker would have created
    """
    prefix, sha, base_branch = cherry_pick_branch.split("-", 2)

    if prefix != "backport":
        raise ValueError(
            'branch name is not prefixed with "backport-". '
            "Is this a cherry_picker branch?"
        )

    if not re.match("[0-9a-f]{7,40}", sha):
        raise ValueError(f"branch name has an invalid sha: {sha}")

    # Validate that the sha refers to a valid commit within the repo
    # Throws a ValueError if the sha is not present in the repo
    validate_sha(sha)

    # Subject the parsed base_branch to the same tests as when we generated it
    # This throws a ValueError if the base_branch doesn't meet our requirements
    compute_version_sort_key(config, base_branch)

    return base_branch


def validate_sha(sha):
    """
    Validate that a hexdigest sha is a valid commit in the repo

    raises ValueError if the sha does not reference a commit within the repo
    """
    cmd = ["git", "log", "--max-count=1", "-r", sha]
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.SubprocessError:
        raise ValueError(
            f"The sha listed in the branch name, {sha}, "
            "is not present in the repository"
        )


def compute_version_sort_key(config, branch):
    """
    Get sort key based on version information from the given git branch name.

    This function can be used as a sort key in list.sort()/sorted() provided that
    you additionally pass config as a first argument by e.g. wrapping it with
    functools.partial().

    Branches with version information come first and are sorted from latest
    to oldest version.
    Branches without version information come second and are sorted alphabetically.
    """
    m = re.search(r"\d+(?:\.\d+)+", branch)
    if m:
        raw_version = m[0].split(".")
        # Use 0 to sort version numbers *before* regular branch names
        return (0, *(-int(x) for x in raw_version))

    if not branch:
        raise ValueError("Branch name is an empty string.")
    if config["require_version_in_branch_name"]:
        raise ValueError(f"Branch {branch} seems to not have a version in its name.")

    # Use 1 to sort regular branch names *after* version numbers
    return (1, branch)


def get_current_branch():
    """
    Return the current branch
    """
    cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    return output.strip().decode("utf-8")


def get_full_sha_from_short(short_sha):
    cmd = ["git", "log", "-1", "--format=%H", short_sha]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    full_sha = output.strip().decode("utf-8")
    return full_sha


def get_author_info_from_short_sha(short_sha):
    cmd = ["git", "log", "-1", "--format=%aN <%ae>", short_sha]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    author = output.strip().decode("utf-8")
    return author


def get_commits_from_backport_branch(cherry_pick_branch):
    cmd = ["git", "log", "--format=%H", f"{cherry_pick_branch}.."]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    commits = output.strip().decode("utf-8").splitlines()
    return commits


def normalize_commit_message(commit_message):
    """
    Return a tuple of title and body from the commit message
    """
    title, _, body = commit_message.partition("\n")
    return title, body.lstrip("\n")


def remove_commit_prefix(commit_message):
    """
    Remove prefix "[X.Y] " from the commit message
    """
    while True:
        m = re.match(r"\[\d+(?:\.\d+)+\] *", commit_message)
        if not m:
            return commit_message
        commit_message = commit_message[m.end() :]


def is_git_repo():
    """Check whether the current folder is a Git repo."""
    cmd = "git", "rev-parse", "--git-dir"
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def find_config(revision):
    """Locate and return the default config for current revision."""
    if not is_git_repo():
        return None

    cfg_path = f"{revision}:.cherry_picker.toml"
    cmd = "git", "cat-file", "-t", cfg_path

    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        path_type = output.strip().decode("utf-8")
        return cfg_path if path_type == "blob" else None
    except subprocess.CalledProcessError:
        return None


def load_config(path=None):
    """Choose and return the config path and it's contents as dict."""
    # NOTE: Initially I wanted to inherit Path to encapsulate Git access
    # there but there's no easy way to subclass pathlib.Path :(
    head_sha = get_sha1_from("HEAD")
    revision = head_sha
    saved_config_path = load_val_from_git_cfg("config_path")
    if not path and saved_config_path is not None:
        path = saved_config_path

    if path is None:
        path = find_config(revision=revision)
    else:
        if ":" not in path:
            path = f"{head_sha}:{path}"

            revision, _col, _path = path.partition(":")
            if not revision:
                revision = head_sha

    config = DEFAULT_CONFIG

    if path is not None:
        config_text = from_git_rev_read(path)
        d = tomllib.loads(config_text)
        config = config.new_child(d)

    return path, config


def get_sha1_from(commitish):
    """Turn 'commitish' into its sha1 hash."""
    cmd = ["git", "rev-parse", commitish]
    try:
        return (
            subprocess.check_output(cmd, stderr=subprocess.PIPE).strip().decode("utf-8")
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(exc.stderr.strip().decode("utf-8"))


def reset_stored_config_ref():
    """Remove the config path option from Git config."""
    try:
        wipe_cfg_vals_from_git_cfg("config_path")
    except subprocess.CalledProcessError:
        """Config file pointer is not stored in Git config."""


def reset_stored_previous_branch():
    """Remove the previous branch information from Git config."""
    wipe_cfg_vals_from_git_cfg("previous_branch")


def reset_state():
    """Remove the progress state from Git config."""
    wipe_cfg_vals_from_git_cfg("state")


def set_state(state):
    """Save progress state into Git config."""
    save_cfg_vals_to_git_cfg(state=state.name)


def get_state():
    """Retrieve the progress state from Git config."""
    return get_state_from_string(load_val_from_git_cfg("state") or "UNSET")


def save_cfg_vals_to_git_cfg(**cfg_map):
    """Save a set of options into Git config."""
    for cfg_key_suffix, cfg_val in cfg_map.items():
        cfg_key = f'cherry-picker.{cfg_key_suffix.replace("_", "-")}'
        cmd = "git", "config", "--local", cfg_key, cfg_val
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)


def wipe_cfg_vals_from_git_cfg(*cfg_opts):
    """Remove a set of options from Git config."""
    for cfg_key_suffix in cfg_opts:
        cfg_key = f'cherry-picker.{cfg_key_suffix.replace("_", "-")}'
        cmd = "git", "config", "--local", "--unset-all", cfg_key
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)


def load_val_from_git_cfg(cfg_key_suffix):
    """Retrieve one option from Git config."""
    cfg_key = f'cherry-picker.{cfg_key_suffix.replace("_", "-")}'
    cmd = "git", "config", "--local", "--get", cfg_key
    try:
        return (
            subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            .strip()
            .decode("utf-8")
        )
    except subprocess.CalledProcessError:
        return None


def from_git_rev_read(path):
    """Retrieve given file path contents of certain Git revision."""
    if ":" not in path:
        raise ValueError("Path identifier must start with a revision hash.")

    cmd = "git", "show", "-t", path
    try:
        return subprocess.check_output(cmd).rstrip().decode("utf-8")
    except subprocess.CalledProcessError:
        raise ValueError


def get_state_from_string(state_str):
    return WORKFLOW_STATES.__members__[state_str]


if __name__ == "__main__":
    cherry_pick_cli()
