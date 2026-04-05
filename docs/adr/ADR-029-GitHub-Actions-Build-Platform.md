# ADR-029: GitHub Actions as Primary Build Execution Platform

**Status**: Accepted
**Date**: 2026-03-01
**Notebook**: NB4 Part 1

## Context

§4.5 defines S4 Build stage with CLI and GUI automation paths. NB1-3 implemented stubs that returned mock success. Real builds require:
- Hermetic execution environments
- Artifact storage and retention
- Build log accessibility
- Cost predictability
- Multi-platform support (Linux, macOS, Windows)

The specification is silent on the specific build execution platform.

## Decision

Use GitHub Actions as the primary build execution platform for all CLI-buildable stacks (React Native, Python Backend, Next.js Web).

**Rationale**:
1. **Already integrated**: GitHub is the code storage platform (NB2 GitHubClient)
2. **Free tier**: 2000 minutes/month for private repos, unlimited for public repos
3. **Workflow dispatch API**: Programmatic trigger with custom inputs
4. **Artifact retention**: 90-day default with downloadable zips
5. **Multi-platform runners**: ubuntu-latest, macos-latest, windows-latest
6. **Secrets management**: Repository secrets for signing keys
7. **Build matrix**: Parallel builds for multiple variants
8. **Status webhooks**: Real-time build notifications (future enhancement)

**Alternatives considered**:
- **Cloud Build (GCP)**: $0.003/build-minute after 120 min/day free tier. More expensive than GitHub Actions for typical usage (4-12 projects/month × 10-15 min/build).
- **Jenkins self-hosted**: Requires dedicated infrastructure, maintenance overhead.
- **CircleCI**: 6000 min/month free but requires separate service integration.

## Consequences

**Positive**:
- No additional service cost (within free tier)
- Single integration point (GitHub)
- Full build history in GitHub UI
- Secrets stored in GitHub (already required for code push)

**Negative**:
- 2000 min/month limit for private repos (sufficient for 130+ builds @ 15 min each)
- If limit exceeded, fall back to Telegram Airlock with manual build instructions

## Implementation

- Workflow templates in `factory/templates/github_actions/`
- `GitHubClient` extended with `dispatch_workflow`, `poll_workflow_status`, `download_artifact`, `commit_workflow_template`
- `S4BuildStage` modified to use GitHub Actions for CLI path
- Budget Governor updated: GitHub Actions cost tracked as $0 for public repos, $0.008/min after 2000 min for private

## References

- §4.5.1 CLI Build Paths
- §2.7 Execution Mode Manager
- Appendix D: No Magic Handoffs #6 (Code→Build)
