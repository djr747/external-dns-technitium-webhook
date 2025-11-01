# Technitium Credential Setupdocker-compose up -d

   ```

This guide explains how to provision and manage credentials for the webhook. Pair it with `docs/deployment/kubernetes.md`, which covers deploying the sidecar.

3. **Audit access logs:**

## Prerequisites   - Check Technitium DNS audit logs

- Technitium DNS Server v5.0 or later   - Review webhook logs for suspicious activity

- Admin access to create users in Technitium

- `kubectl` access to the cluster running ExternalDNS (Helm 3 recommended)4. **Update all instances:**

   - Ensure all deployments use new credentials

## 1. Create a Dedicated Technitium User   - Check for any hardcoded values

1. Sign in to the Technitium DNS web console (`http://<dns-host>:5380`).

2. Navigate to **Administration → Users → Add User**.## Troubleshooting

3. Choose a descriptive username such as `external-dns-webhook`.

4. Grant only DNS permissions required for zone read/write and record management.### Authentication Failures

5. Generate a long, random password (`openssl rand -base64 32`).

6. Save the user and store the password securely.**Symptom:** "Invalid credentials" or "Login failed"



Using a dedicated account keeps audit trails clear and allows rotation without impacting other services.**Solutions:**

1. Verify username and password are correct

## 2. Store the Credentials in Kubernetes2. Check user has DNS permissions in Technitium

Create the namespace if needed, then load the credentials into a secret:3. Ensure user is not disabled

4. Try logging in via web console with same credentials

```bash

kubectl create namespace external-dns --dry-run=client -o yaml | kubectl apply -f -### Connection Refused



kubectl create secret generic technitium-credentials \**Symptom:** "Connection refused" or "Cannot connect to server"

  --from-literal=username='external-dns-webhook' \

  --from-literal=password='REPLACE-ME' \**Solutions:**

  --namespace=external-dns1. Verify `TECHNITIUM_URL` is correct

```2. Check network connectivity: `curl http://your-dns-server:5380`

3. Ensure firewall allows connections

Reference the secret from your Helm values or manifest:4. Verify DNS server is running



```yaml### Token Expiration

env:

  - name: TECHNITIUM_USERNAME**Symptom:** "Invalid or expired token"

    valueFrom:

      secretKeyRef:**Solutions:**

        name: technitium-credentials- The webhook automatically renews tokens

        key: username- If persistent, check logs for renewal errors

  - name: TECHNITIUM_PASSWORD- Verify credentials are still valid

    valueFrom:

      secretKeyRef:### Permission Denied

        name: technitium-credentials

        key: password**Symptom:** "Permission denied" or "Insufficient privileges"

```

**Solutions:**

For local testing, export the same values or place them in a `.env` file (restrict permissions with `chmod 600 .env`).1. Verify user has DNS permissions

2. Check zone permissions

## 3. Provide Endpoint Details3. Ensure user can create/modify records

Set the Technitium API URL and optional domain filters/failover targets. Example:

## Advanced Configuration

```bash

export TECHNITIUM_URL="http://technitium-dns.technitium.svc.cluster.local:5380"### Using HashiCorp Vault

export TECHNITIUM_FAILOVER_URLS="http://dns-backup:5380;http://dns-dr:5380"

export ZONE="example.com"```yaml

export DOMAIN_FILTERS="example.com;dev.example.com"apiVersion: apps/v1

```kind: Deployment

metadata:

These variables correspond to the fields in `external_dns_technitium_webhook.config.Config`; see the table in `README.md` for all options.  name: technitium-webhook

spec:

## 4. Verify Connectivity  template:

After deploying the webhook sidecar (see `docs/deployment/kubernetes.md`):    metadata:

      annotations:

```bash        vault.hashicorp.com/agent-inject: "true"

kubectl logs -n external-dns deployment/external-dns -c webhook --tail=20        vault.hashicorp.com/role: "technitium-webhook"

kubectl exec -n external-dns deploy/external-dns -c webhook -- curl -s http://127.0.0.1:3000/health        vault.hashicorp.com/agent-inject-secret-credentials: "secret/data/technitium"

```    spec:

      containers:

`200 OK` indicates the webhook authenticated with Technitium and is ready.      - name: webhook

        image: ghcr.io/yourusername/external-dns-technitium-webhook:latest

## 5. Rotate Credentials        env:

1. Rotate the password (or create a new user) in Technitium.        - name: TECHNITIUM_USERNAME

2. Update the Kubernetes secret:          valueFrom:

   ```bash            secretKeyRef:

   kubectl create secret generic technitium-credentials \              name: vault-secret

     --from-literal=username='external-dns-webhook' \              key: username

     --from-literal=password='NEW-PASSWORD' \        - name: TECHNITIUM_PASSWORD

     --namespace=external-dns \          valueFrom:

     --dry-run=client -o yaml | kubectl apply -f -            secretKeyRef:

   ```              name: vault-secret

3. Restart the ExternalDNS deployment so the sidecar reloads the secret:              key: password

   ```bash```

   kubectl rollout restart deployment/external-dns -n external-dns

   ```### Using External Secrets Operator

4. Confirm the `/health` endpoint returns `200` again.

```yaml

## Security TipsapiVersion: external-secrets.io/v1beta1

- Keep secrets out of source control; ensure `.env` files stay in `.gitignore`.kind: ExternalSecret

- Restrict namespace and secret access with Kubernetes RBAC and audit logging.metadata:

- Review webhook logs for repeated authentication failures and rotate credentials on a regular cadence (roughly every 90 days in production).  name: technitium-credentials

spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: SecretStore
  target:
    name: technitium-webhook-credentials
  data:
  - secretKey: TECHNITIUM_USERNAME
    remoteRef:
      key: technitium/webhook
      property: username
  - secretKey: TECHNITIUM_PASSWORD
    remoteRef:
      key: technitium/webhook
      property: password
```

## Security Checklist

Before deploying to production, verify:

- [ ] Dedicated user account created (not using admin)
- [ ] Strong password (20+ characters, generated)
- [ ] Credentials stored in secure secret store
- [ ] No credentials in source code or version control
- [ ] `.env` files added to `.gitignore`
- [ ] File permissions set correctly (`chmod 600 .env`)
- [ ] RBAC configured in Kubernetes
- [ ] Pod security policies/admission controllers enabled
- [ ] Network policies restrict access to DNS server
- [ ] Logging enabled for audit trail
- [ ] Credential rotation schedule established
- [ ] Incident response plan documented

## Additional Resources

- [Technitium DNS Server Documentation](https://technitium.com/dns/)
- [Kubernetes Secrets Management](https://kubernetes.io/docs/concepts/configuration/secret/)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [12-Factor App: Config](https://12factor.net/config)

## High Availability (HA) deployments — important note

When running the webhook in a highly-available configuration (multiple ExternalDNS replicas / multiple webhook sidecar replicas), ensure the Technitium service account credentials are identical across all replicas:

- `TECHNITIUM_USERNAME` must be the same for every replica
- `TECHNITIUM_PASSWORD` must be the same for every replica

Reason: the webhook manages tokens and authentication state with the Technitium API; if replicas use different credentials or different service accounts, the tokens may not be interchangeable and authentication failures can occur during failover or rolling updates. Use a single Kubernetes Secret (referenced by all replicas) or a centralized secrets manager (HashiCorp Vault, ExternalSecrets) to ensure all replicas use the same credentials.

See `docs/deployment/kubernetes.md` for examples of how to mount or inject a single credential secret into all webhook sidecars.
