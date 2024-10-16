# Release Checklist

- [ ] check tests pass on [GitHub Actions](https://github.com/python/cherry-picker/actions)
      [![GitHub Actions status](https://github.com/python/cherry-picker/actions/workflows/main.yml/badge.svg)](https://github.com/python/cherry-picker/actions/workflows/main.yml)

- [ ] Update [changelog](https://github.com/python/cherry-picker/blob/main/CHANGELOG.md)

- [ ] Go to the [Releases page](https://github.com/python/cherry-picker/releases) and

  - [ ] Click "Draft a new release"

  - [ ] Click "Choose a tag"

  - [ ] Type the next `cherry-picker-vX.Y.Z` version and select "**Create new tag: cherry-picker-vX.Y.Z** on publish"

  - [ ] Leave the "Release title" blank (it will be autofilled)

  - [ ] Click "Generate release notes" and amend as required

  - [ ] Click "Publish release"

- [ ] Check the tagged [GitHub Actions build](https://github.com/python/cherry-picker/actions/workflows/deploy.yml)
      has deployed to [PyPI](https://pypi.org/project/cherry_picker/#history)

- [ ] Check installation:

  ```bash
  python -m pip uninstall -y cherry_picker && python -m pip install -U cherry_picker && cherry_picker --version
  ```
