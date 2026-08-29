# The one thing Terraform does not create

Everything in this project is created by `terraform apply` except one value: the
OAuth 2.0 Web client ID that Google sign-in tokens are minted for.

That is not a shortcut taken to save time. Google exposes OAuth client creation
through its API only for consent screens marked **internal**, which requires a
Google Workspace organisation. This project sits under a personal account, so
the consent screen must be **external**, and external clients have no Terraform
resource, no `gcloud` command, and no REST endpoint. It is a console operation
or it does not happen.

So the value is created once by hand. Everything downstream of it is Terraform's:
it arrives as a GitHub secret, becomes an environment variable on Cloud Run, and
the API reads it from there.

## Until it is set, nobody can sign in

`api/app/auth.py` refuses every bearer token while `TRIMBIN_OAUTH_CLIENT_ID` is
empty, and logs an error saying so on each attempt.

That is deliberate and it is the safe direction to fail. Verifying a Google ID
token without naming an audience checks the signature and the issuer and then
accepts it — so *any* valid Google ID token, minted for any application in the
world, would be honoured. A member who signed into an unrelated site with Google
could have that site's token replayed against us. A deployment where nobody can
sign in is a visible problem; one where anybody can is not.

The public pages and the demo project do not need a token and are
unaffected.

## What to click

1. **APIs & Services → OAuth consent screen**, in the `trimbin` project.
   - User type: **External**
   - App name: `Trimbin`
   - User support email and developer contact: `tanvir4hmed@gmail.com`
   - Scopes: none beyond the defaults. Trimbin needs an email address and
     nothing else, and every scope added here is one a user is asked to grant.
   - Test users: the three team addresses, while the app is unverified.
     Publishing is not required for the demo and starts a review process.

2. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Web application**
   - Name: `Trimbin web`
   - Authorised JavaScript origins:
     - `https://trimbin.qlitch.com`
     - `http://localhost:3000`
   - Authorised redirect URIs: none. Sign-in uses Google Identity Services,
     which returns a credential to the page rather than redirecting.

3. Copy the client ID. It looks like `NNNNNNNN-xxxx.apps.googleusercontent.com`.

## Where to put it

```bash
gh secret set OAUTH_CLIENT_ID --body "NNNNNNNN-xxxx.apps.googleusercontent.com"
```

`--body`, not a pipe. A piped value carries a trailing newline into the secret,
and a client ID with a newline in it fails audience verification with an error
that names the token rather than the whitespace.

Push, and the next deploy carries it. Nothing else needs doing.

## A note on secrecy

A client ID is not a secret. It is embedded in every page that loads the sign-in
button and is visible to anyone who views source. It lives in GitHub secrets only
because that is where deployment configuration lives, not because it needs
protecting. The client *secret* — which this flow never uses — would be
different, and is why the flow does not use one.
