# cherry_picker

[![PyPI version](https://img.shields.io/pypi/v/cherry-picker.svg?logo=pypi&logoColor=FFE873)](https://pypi.org/project/cherry-picker)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/cherry-picker.svg?logo=python&logoColor=FFE873)](https://pypi.org/project/cherry-picker)
[![tests](https://github.com/python/cherry-picker/actions/workflows/main.yml/badge.svg)](https://github.com/python/cherry-picker/actions/workflows/main.yml)

Usage (from a cloned CPython directory):

```
Usage: cherry_picker [OPTIONS] [COMMIT_SHA1] [BRANCHES]...

  cherry-pick COMMIT_SHA1 into target BRANCHES.

Options:
  --version                  Show the version and exit.
  --dry-run                  Prints out the commands, but not executed.
  --pr-remote REMOTE         git remote to use for PR branches
  --upstream-remote REMOTE   git remote to use for upstream branches
  --abort                    Abort current cherry-pick and clean up branch
  --continue                 Continue cherry-pick, push, and clean up branch
  --status                   Get the status of cherry-pick
  --push / --no-push         Changes won't be pushed to remote
  --auto-pr / --no-auto-pr   If auto PR is enabled, cherry-picker will
                             automatically open a PR through API if GH_AUTH
                             env var is set, or automatically open the PR
                             creation page in the web browser otherwise.
  --config-path CONFIG-PATH  Path to config file, .cherry_picker.toml from
                             project root by default. You can prepend a colon-
                             separated Git 'commitish' reference.
  -h, --help                 Show this message and exit.
```

## About

This tool is used to backport CPython changes from `main` into one or more
of the maintenance branches (e.g. `3.12`, `3.11`).

`cherry_picker` can be configured to backport other projects with similar
workflow as CPython. See the configuration file options below for more details.

The maintenance branch names should contain some sort of version number (`X.Y`).
For example: `3.12`, `stable-3.12`, `1.5`, `1.5-lts`, are all supported branch
names.

It will prefix the commit message with the branch, e.g. `[3.12]`, and then
open up the pull request page.

Write tests using [pytest](https://docs.pytest.org/).


## Setup info

```console
$ python3 -m venv venv
$ source venv/bin/activate
(venv) $ python -m pip install cherry_picker
```

The cherry-picking script assumes that if an `upstream` remote is defined, then
it should be used as the source of upstream changes and as the base for
cherry-pick branches. Otherwise, `origin` is used for that purpose.
You can override this behavior with the `--upstream-remote` option
(e.g. `--upstream-remote python` to use a remote named `python`).

Verify that an `upstream` remote is set to the CPython repository:

```console
$ git remote -v
...
upstream	https://github.com/python/cpython (fetch)
upstream	https://github.com/python/cpython (push)
```

If needed, create the `upstream` remote:

```console
$ git remote add upstream https://github.com/python/cpython.git
```

By default, the PR branches used to submit pull requests back to the main
repository are pushed to `origin`. If this is incorrect, then the correct
remote will need be specified using the `--pr-remote` option (e.g.
`--pr-remote pr` to use a remote named `pr`).


## Cherry-picking 🐍🍒⛏️

(Setup first! See previous section.)

From the cloned CPython directory:

```console
(venv) $ cherry_picker [--pr-remote REMOTE] [--upstream-remote REMOTE] [--dry-run] [--config-path CONFIG-PATH] [--abort/--continue] [--status] [--push/--no-push] [--auto-pr/--no-auto-pr] <commit_sha1> <branches>
```

### Commit sha1

The commit sha1 for cherry-picking is the squashed commit that was merged to
the `main` branch.  On the merged pull request, scroll to the bottom of the
page.  Find the event that says something like:

```
<coredeveloper> merged commit <commit_sha1> into python:main <sometime> ago.
```

By following the link to `<commit_sha1>`, you will get the full commit hash.
Use the full commit hash for `cherry_picker.py`.


### Options

```
--dry-run                 Dry Run Mode.  Prints out the commands, but not executed.
--pr-remote REMOTE        Specify the git remote to push into.  Default is 'origin'.
--upstream-remote REMOTE  Specify the git remote to use for upstream branches.
                          Default is 'upstream' or 'origin' if the former doesn't exist.
--status                  Do `git status` in cpython directory.
```

Additional options:

```
--abort        Abort current cherry-pick and clean up branch
--continue     Continue cherry-pick, push, and clean up branch
--no-push      Changes won't be pushed to remote
--no-auto-pr   PR creation page won't be automatically opened in the web browser or
               if GH_AUTH is set, the PR won't be automatically opened through API.
--config-path  Path to config file
               (`.cherry_picker.toml` from project root by default)
```

Configuration file example:

```toml
team = "aio-libs"
repo = "aiohttp"
check_sha = "f382b5ffc445e45a110734f5396728da7914aeb6"
fix_commit_msg = false
default_branch = "devel"
require_version_in_branch_name = false
draft_pr = false
```

Available config options:

```
team                            github organization or individual nick,
                                e.g "aio-libs" for https://github.com/aio-libs/aiohttp
                                ("python" by default)

repo                            github project name,
                                e.g "aiohttp" for https://github.com/aio-libs/aiohttp
                                ("cpython" by default)

check_sha                       A long hash for any commit from the repo,
                                e.g. a sha1 hash from the very first initial commit
                                ("7f777ed95a19224294949e1b4ce56bbffcb1fe9f" by default)

fix_commit_msg                  Replace # with GH- in cherry-picked commit message.
                                It is the default behavior for CPython because of external
                                Roundup bug tracker (https://bugs.python.org) behavior:
                                #xxxx should point on issue xxxx but GH-xxxx points
                                on pull-request xxxx.
                                For projects using GitHub Issues, this option can be disabled.

default_branch                  Project's default branch name,
                                e.g "devel" for https://github.com/ansible/ansible
                                ("main" by default)

require_version_in_branch_name  Allow backporting to branches whose names don't contain
                                something that resembles a version number
                                (i.e. at least two dot-separated numbers).

draft_pr                        Create PR as draft
                                (false by default)
```

To customize the tool for used by other project:

1. Create a file called `.cherry_picker.toml` in the project's root
   folder (alongside with `.git` folder).

2. Add `team`, `repo`, `fix_commit_msg`, `check_sha` and
   `default_branch` config values as described above.

3. Use `git add .cherry_picker.toml` / `git commit` to add the config
   into Git.

4. Add `cherry_picker` to development dependencies or install it
   by `pip install cherry_picker`

5. Now everything is ready, use `cherry_picker <commit_sha> <branch1>
   <branch2>` for cherry-picking changes from `<commit_sha>` into
   maintenance branches.
   Branch name should contain at least major and minor version numbers
   and may have some prefix or suffix.
   Only the first version-like substring is matched when the version
   is extracted from branch name.

### Demo

- Installation: https://asciinema.org/a/125254

- Backport: https://asciinema.org/a/125256


### Example

For example, to cherry-pick `6de2b7817f-some-commit-sha1-d064` into
`3.12` and `3.11`, run the following command from the cloned CPython
directory:

```console
(venv) $ cherry_picker 6de2b7817f-some-commit-sha1-d064 3.12 3.11
```

What this will do:

```console
(venv) $ git fetch upstream

(venv) $ git checkout -b backport-6de2b78-3.12 upstream/3.12
(venv) $ git cherry-pick -x 6de2b7817f-some-commit-sha1-d064
(venv) $ git push origin backport-6de2b78-3.12
(venv) $ git checkout main
(venv) $ git branch -D backport-6de2b78-3.12

(venv) $ git checkout -b backport-6de2b78-3.11 upstream/3.11
(venv) $ git cherry-pick -x 6de2b7817f-some-commit-sha1-d064
(venv) $ git push origin backport-6de2b78-3.11
(venv) $ git checkout main
(venv) $ git branch -D backport-6de2b78-3.11
```

In case of merge conflicts or errors, the following message will be displayed:

```
Failed to cherry-pick 554626ada769abf82a5dabe6966afa4265acb6a6 into 2.7 :frowning_face:
... Stopping here.

To continue and resolve the conflict:
    $ cherry_picker --status  # to find out which files need attention
    # Fix the conflict
    $ cherry_picker --status  # should now say 'all conflict fixed'
    $ cherry_picker --continue

To abort the cherry-pick and cleanup:
    $ cherry_picker --abort
```

Passing the `--dry-run` option will cause the script to print out all the
steps it would execute without actually executing any of them. For example:

```console
$ cherry_picker --dry-run --pr-remote pr 1e32a1be4a1705e34011770026cb64ada2d340b5 3.12 3.11
Dry run requested, listing expected command sequence
fetching upstream ...
dry_run: git fetch origin
Now backporting '1e32a1be4a1705e34011770026cb64ada2d340b5' into '3.12'
dry_run: git checkout -b backport-1e32a1b-3.12 origin/3.12
dry_run: git cherry-pick -x 1e32a1be4a1705e34011770026cb64ada2d340b5
dry_run: git push pr backport-1e32a1b-3.12
dry_run: Create new PR: https://github.com/python/cpython/compare/3.12...ncoghlan:backport-1e32a1b-3.12?expand=1
dry_run: git checkout main
dry_run: git branch -D backport-1e32a1b-3.12
Now backporting '1e32a1be4a1705e34011770026cb64ada2d340b5' into '3.11'
dry_run: git checkout -b backport-1e32a1b-3.11 origin/3.11
dry_run: git cherry-pick -x 1e32a1be4a1705e34011770026cb64ada2d340b5
dry_run: git push pr backport-1e32a1b-3.11
dry_run: Create new PR: https://github.com/python/cpython/compare/3.11...ncoghlan:backport-1e32a1b-3.11?expand=1
dry_run: git checkout main
dry_run: git branch -D backport-1e32a1b-3.11
```

### `--pr-remote` option

This will generate pull requests through a remote other than `origin`
(e.g. `pr`)

### `--upstream-remote` option

This will generate branches from a remote other than `upstream`/`origin`
(e.g. `python`)

### `--status` option

This will do `git status` for the CPython directory.

### `--abort` option

Cancels the current cherry-pick and cleans up the cherry-pick branch.

### `--continue` option

Continues the current cherry-pick, commits, pushes the current branch to
`origin`, opens the PR page, and cleans up the branch.

### `--no-push` option

Changes won't be pushed to remote.  This allows you to test and make additional
changes.  Once you're satisfied with local changes, use `--continue` to complete
the backport, or `--abort` to cancel and clean up the branch.  You can also
cherry-pick additional commits, by:

```console
$ git cherry-pick -x <commit_sha1>
```

### `--no-auto-pr` option

PR creation page won't be automatically opened in the web browser or
if GH_AUTH is set, the PR won't be automatically opened through API.
This can be useful if your terminal is not capable of opening a useful web browser,
or if you use cherry-picker with a different Git hosting than GitHub.

### `--config-path` option

Allows to override default config file path
(`<PROJ-ROOT>/.cherry_picker.toml`) with a custom one. This allows cherry_picker
to backport projects other than CPython.


## Creating pull requests

When a cherry-pick was applied successfully, this script will open up a browser
tab that points to the pull request creation page.

The url of the pull request page looks similar to the following:

```
https://github.com/python/cpython/compare/3.12...<username>:backport-6de2b78-3.12?expand=1
```

Press the `Create Pull Request` button.

Bedevere will then remove the `needs backport to ...` label from the original
pull request against `main`.


## Running tests

```console
$ # Install pytest
$ pip install -U pytest
$ # Run tests
$ pytest
```

Tests require your local version of Git to be 2.28.0+.

## Publishing to PyPI

- See the [release checklist](https://github.com/python/cherry-picker/blob/main/RELEASING.md).


## Local installation

In the directory where `pyproject.toml` exists:

```console
$ pip install
```

## Changelog

See the [changelog](https://github.com/python/cherry-picker/blob/main/CHANGELOG.md).
