# Security Policy

## Reporting a Vulnerability

We take the security of the Beszel Hub charm seriously. If you believe you have found a security vulnerability, please report it to us responsibly.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them using GitHub's Security Advisory feature:

1. Navigate to the repository on GitHub
2. Click on the "Security" tab
3. Click "Report a vulnerability"
4. Fill out the form with details about the vulnerability

Alternatively, you can email security reports to: [security@example.com]

### What to Include

Please include the following information in your report:

- Type of vulnerability (e.g., authentication bypass, privilege escalation, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### What to Expect

- You will receive an acknowledgment of your report within 48 hours
- We will send a more detailed response within 7 days indicating the next steps
- We will keep you informed about the progress toward a fix and announcement
- We may ask for additional information or guidance

### Disclosure Policy

- Security issues are typically disclosed once a fix is available
- We follow coordinated disclosure practices
- Credit will be given to researchers who report vulnerabilities responsibly

## Supported Versions

Security updates are provided for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| latest (main) | :white_check_mark: |
| < 1.0   | :x:                |

## Security Best Practices

When deploying and using this charm:

1. **Always use the latest version** of the charm from the stable channel
2. **Enable OAuth/OIDC** for production deployments instead of relying solely on password authentication
3. **Use ingress with TLS** to encrypt traffic to the Beszel Hub
4. **Regularly backup your data** using the S3 integration or backup actions
5. **Restrict network access** to the Beszel Hub using Kubernetes network policies
6. **Review audit logs** regularly for suspicious activity
7. **Keep Juju and Kubernetes up to date** with security patches

## Known Security Considerations

### OAuth Client Secrets

OAuth client secrets are managed by Juju secrets and are only accessible to the charm. These secrets are never logged or exposed in status messages.

### S3 Credentials

S3 credentials are obtained from the s3-integrator relation and are stored securely by Juju. They are not logged or exposed in charm output.

### Database Security

The PocketBase database is stored in a Kubernetes persistent volume with appropriate file permissions. Access is restricted to the Beszel container only.

## Additional Resources

- [Juju Security Documentation](https://juju.is/docs/juju/security)
- [Kubernetes Security Best Practices](https://kubernetes.io/docs/concepts/security/)
- [Beszel Security](https://beszel.dev/)
