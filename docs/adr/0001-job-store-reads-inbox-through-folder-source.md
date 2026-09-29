# The Job store reads its inbox through the Folder adapter

The Job store writes Alerts to `emails/` itself but reads them back, together with hand-dropped files in `samples/`, through the Folder adapter of the Alert source. We keep this split on purpose: it has caused no bugs, and the only change that gives the Job store sole ownership of its inbox is to import samples through `fetch`, so a dropped-in sample would only show up after the next `fetch` or `run`.

## Considered Options

- **Job store reads `emails/` itself, Folder adapter keeps `samples/`.** Rejected: the Job store still depends on the Alert source, so nothing is gained.
- **Samples become an Alert source that `fetch` imports into the inbox.** Rejected: delays dropped-in samples, and the import must keep working when Outlook sign-in fails.
