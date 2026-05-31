# Quiz: Fixing the Broken `.gitlab-ci.yml`

## The broken file

```yaml
stages:
  - unittest
  -security-scan

security_scan:
  stage: security-scan
  script:
    - trivy repo ./
```

## What is wrong

### Primary bug — missing space in the list item (line 3)

```yaml
  -security-scan   # WRONG
```

In YAML, a list item requires a space after the `-`. Without it, `-security-scan`
is **not** parsed as a list item; it is read as a scalar string. As a result the
stage `security-scan` is never registered in `stages`.

The job `security_scan` then references `stage: security-scan`, a stage that does
not exist, so GitLab rejects the pipeline (error along the lines of
*"chosen stage security-scan does not exist"*).

**Fix:** add the missing space.

```yaml
  - security-scan   # CORRECT
```

### Secondary issue — unused stage `unittest`

The stage `unittest` is declared but no job uses it. This does not break the
pipeline, but it is a dead stage. Either remove it, or add a job that uses it.

## Corrected file

```yaml
stages:
  - unittest
  - security-scan

unittest:
  stage: unittest
  script:
    - echo "Running unit tests..."

security_scan:
  stage: security-scan
  script:
    - trivy repo ./
```

## One-line answer

The bug is on line 3: `-security-scan` is missing the space after the dash, so the
`security-scan` stage is never registered and the job referencing it fails. Fix it
by writing `- security-scan`.
