# Changelog

## 2.5.0

* Add draft config option to Create Pull Request by @gopidesupavan in https://github.com/python/cherry-picker/pull/151
* Better error message when cherry_picker is called in wrong state by @serhiy-storchaka in https://github.com/python/cherry-picker/pull/119
* Bubble up error message by @dpr-0 in https://github.com/python/cherry-picker/pull/112
* Acknowledge network issues on GitHub by @ambv in https://github.com/python/cherry-picker/pull/153
* Ignore uv.lock file by @potiuk in https://github.com/python/cherry-picker/pull/149
* Fix mypy pre-commit settings by @potiuk in https://github.com/python/cherry-picker/pull/148
* Update CI config by @hugovk in https://github.com/python/cherry-picker/pull/144

## 2.4.0

- Add support for Python 3.14 ([PR 145](https://github.com/python/cherry-picker/pull/145))
- Allow passing a base branch that doesn't have version info
  ([PR 70](https://github.com/python/cherry-picker/pull/70))
  - This makes cherry-picker useful for projects other than CPython that don't
    have versioned branch names.

## 2.3.0

- Add support for Python 3.13
  ([PR 127](https://github.com/python/cherry-picker/pull/127),
  [PR 134](https://github.com/python/cherry-picker/pull/134))
- Drop support for EOL Python 3.8
  ([PR 133](https://github.com/python/cherry-picker/pull/133),
  [PR 137](https://github.com/python/cherry-picker/pull/137))
- Resolve usernames when the remote ends with a trailing slash ([PR 110](https://github.com/python/cherry-picker/pull/110))
- Optimize `validate_sha()` with `--max-count=1` ([PR 111](https://github.com/python/cherry-picker/pull/111))
- Make # replacing more strict ([PR 115](https://github.com/python/cherry-picker/pull/115))
- Remove multiple commit prefixes ([PR 118](https://github.com/python/cherry-picker/pull/118))
- Handle whitespace when calculating usernames ([PR 132](https://github.com/python/cherry-picker/pull/132))
- Publish to PyPI using Trusted Publishers ([PR 94](https://github.com/python/cherry-picker/pull/94))
- Generate digital attestations for PyPI ([PEP 740](https://peps.python.org/pep-0740/))
  ([PR 135](https://github.com/python/cherry-picker/pull/135))

## 2.2.0

- Add log messages
- Fix for conflict handling, get the state correctly ([PR 88](https://github.com/python/cherry-picker/pull/88))
- Drop support for Python 3.7 ([PR 90](https://github.com/python/cherry-picker/pull/90))

## 2.1.0

- Mix fixes: #28, #29, #31, #32, #33, #34, #36

## 2.0.0

- Support the `main` branch by default ([PR 23](https://github.com/python/cherry-picker/pull/23)).
  To use a different default branch, please configure it in the
  `.cherry-picker.toml` file.

 - Renamed `cherry-picker`'s own default branch to `main`

## 1.3.2

- Use `--no-tags` option when fetching upstream ([PR 319](https://github.com/python/core-workflow/pull/319))

## 1.3.1

- Modernize cherry_picker's pyproject.toml file ([PR #316](https://github.com/python/core-workflow/pull/316))

- Remove the `BACKPORT_COMPLETE` state. Unset the states when backport is completed
  ([PR #315](https://github.com/python/core-workflow/pull/315))

- Run Travis CI test on Windows ([PR #311](https://github.com/python/core-workflow/pull/311))

## 1.3.0

- Implement state machine and storing reference to the config
  used at the beginning of the backport process using commit sha
  and a repo-local Git config.
  ([PR #295](https://github.com/python/core-workflow/pull/295))

## 1.2.2

- Relaxed click dependency ([PR #302](https://github.com/python/core-workflow/pull/302))

## 1.2.1

- Validate the branch name to operate on with `--continue` and fail early if the branch could not
  have been created by cherry_picker ([PR #266](https://github.com/python/core-workflow/pull/266))

- Bugfix: Allow `--continue` to support version branches that have dashes in them.  This is
  a bugfix of the additional branch versioning schemes introduced in 1.2.0.
  ([PR #265](https://github.com/python/core-workflow/pull/265)).

- Bugfix: Be explicit about the branch name on the remote to push the cherry pick to.  This allows
  cherry_picker to work correctly when the user has a git push strategy other than the default
  configured ([PR #264](https://github.com/python/core-workflow/pull/264)).

## 1.2.0

- Add `default_branch` configuration item. The default is `master`, which
  is the default branch for CPython. It can be configured to other branches like,
  `devel`, or `develop`.  The default branch is the branch cherry_picker
  will return to after backporting ([PR #254](https://github.com/python/core-workflow/pull/254)
  and [Issue #250](https://github.com/python/core-workflow/issues/250)).

- Support additional branch versioning schemes, such as `something-X.Y`,
  or `X.Y-somethingelse`. ([PR #253](https://github.com/python/core-workflow/pull/253)
  and [Issue #251](https://github.com/python/core-workflow/issues/251)).

## 1.1.1

- Change the calls to `subprocess` to use lists instead of strings. This fixes
  the bug that affects users in Windows
  ([PR #238](https://github.com/python/core-workflow/pull/238)).

## 1.1.0

- Add `fix_commit_msg` configuration item. Setting fix_commit_msg to `true`
  will replace the issue number in the commit message, from `#` to `GH-`.
  This is the default behavior for CPython. Other projects can opt out by
  setting it to `false` ([PR #233](https://github.com/python/core-workflow/pull/233)
  and [aiohttp issue #2853](https://github.com/aio-libs/aiohttp/issues/2853)).

## 1.0.0

- Support configuration file by using `--config-path` option, or by adding
  `.cherry-picker.toml` file to the root of the project
  ([Issue #225](https://github.com/python/core-workflow/issues/225))
