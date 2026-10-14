Attempting to perform the InitializeDefaultDrives operation on the 'FileSystem' provider failed.
# C-Crate feedback reporting

The signed-in C-Crate sidebar has **More → Report feedback**. Reports include a type and description and are sent to the `Spraten/ccrate` GitHub repository. GitHub issues are public, so the form warns users not to include passwords, badge keys, or other sensitive data.

The gateway authenticates each request through Homebox `/api/v1/users/self`; the actor ID comes from that response and is used to scope saved request status. A server-side SQLite database at `WORKSHOP_ROOT/work/ops/feedback-reports.db` keeps request identity and result state and is included in the private deployment backup. Report submission is limited to five new reports per actor per hour, and status reconciliation is throttled per request.

## Configure GitHub delivery

Set `CCRATE_GITHUB_TOKEN` in the **gateway service environment only**. The token needs permission to create issues in the configured repository. The repository defaults to `Spraten/ccrate`; `CCRATE_GITHUB_REPOSITORY` can override it for a private test repository. Never put the token in the frontend, static assets, browser storage, or a checked-in file.

For the Pi's systemd user service, create a protected environment file outside the checkout and reference it from a service drop-in:

```sh
install -d -m 700 "$HOME/.config"
install -m 600 /dev/null "$HOME/.config/ccrate-feedback.env"
nano "$HOME/.config/ccrate-feedback.env"
```

Put this line in the file, replacing the example with a GitHub token that can create issues in the repository:

```text
CCRATE_GITHUB_TOKEN=github_pat_your_token_here
```

Then run `systemctl --user edit homebox-workshop-gateway.service` and add:

```ini
[Service]
EnvironmentFile=%h/.config/ccrate-feedback.env
```

Save the drop-in, then apply it with `systemctl --user daemon-reload` and restart the gateway with `systemctl --user restart homebox-workshop-gateway.service`. The file stays outside the checkout and is readable only by the service account. Do not place the token in source control or a release manifest.

If the token is missing, the endpoint returns a setup error before creating a server request, and the browser keeps the draft. If GitHub times out after a create may have succeeded, C-Crate marks the request pending and never repeats the POST. **Check report status** searches GitHub for the request's unique marker; it keeps the request pending if GitHub cannot confirm it. The same browser draft and request key remain available for later reconciliation.
