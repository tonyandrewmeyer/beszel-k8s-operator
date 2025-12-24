# Beszel Hub Tutorial

This tutorial will guide you through deploying and configuring the Beszel Hub charm on Kubernetes using Juju.

## Prerequisites

Before you begin, ensure you have:

- A Kubernetes cluster (MicroK8s, GKE, EKS, AKS, etc.)
- Juju 3.1+ installed and bootstrapped to your Kubernetes cluster
- `kubectl` access to your cluster
- Basic familiarity with Juju concepts (applications, units, relations)

## Step 1: Deploy Beszel Hub

First, deploy the Beszel Hub charm with persistent storage:

```bash
juju deploy beszel --channel=edge \
  --storage beszel-data=5G
```

Wait for the deployment to complete:

```bash
juju wait-for application beszel --query='status=="active"'
```

Check the status:

```bash
juju status beszel
```

You should see the unit in `active` state.

## Step 2: Access the Admin Interface

Retrieve the admin URL:

```bash
juju run beszel/0 get-admin-url
```

If you haven't configured ingress yet, you can use port forwarding:

```bash
kubectl port-forward -n <model-name> service/beszel 8090:8090
```

Then access http://localhost:8090 in your browser.

## Step 3: Create Admin Account

1. Open the Beszel Hub URL in your browser
2. Click "Create Admin Account"
3. Enter your email and password
4. Click "Create Account"

You're now logged into Beszel Hub!

## Step 4: Configure External Access with Ingress

For production use, configure ingress for external access:

```bash
# Deploy nginx-ingress-integrator
juju deploy nginx-ingress-integrator --trust

# Configure your hostname
juju config nginx-ingress-integrator \
  service-hostname=beszel.example.com

# Integrate with Beszel
juju integrate beszel nginx-ingress-integrator
```

Wait for the integration to complete:

```bash
juju wait-for application beszel
juju wait-for application nginx-ingress-integrator
```

Now you can access Beszel at https://beszel.example.com (make sure DNS is configured).

## Step 5: Add Your First Monitoring System

### Generate an Agent Token

```bash
juju run beszel/0 create-agent-token description="my-first-server"
```

Copy the token from the output.

### Install Beszel Agent

On the system you want to monitor, install the Beszel agent. Using Docker:

```bash
docker run -d \
  --name beszel-agent \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  henrygd/beszel-agent
```

### Configure the Agent

Get your hub URL:

```bash
juju run beszel/0 get-admin-url
```

Configure the agent with the hub URL and token:

```bash
docker exec beszel-agent /beszel-agent configure \
  --hub-url https://beszel.example.com \
  --token <your-token-here>
```

### Add System in Hub

1. Log into Beszel Hub
2. Click "Add System"
3. Enter system details:
   - Name: my-first-server
   - Host: (agent will connect automatically)
4. Click "Add"

You should now see metrics flowing from your monitored system!

## Step 6: Enable OAuth/OIDC Authentication (Optional)

For enterprise deployments, enable SSO:

```bash
# Set external hostname first
juju config beszel external-hostname=beszel.example.com

# Deploy identity platform
juju deploy identity-platform --channel=edge --trust

# Integrate
juju integrate beszel:oauth identity-platform:oauth
```

Wait for the integration:

```bash
juju wait-for application identity-platform
```

Now you can log in using your OAuth provider configured in the identity platform!

## Step 7: Set Up Automated Backups

Configure S3 backups for data protection:

```bash
# Deploy S3 integrator
juju deploy s3-integrator

# Configure S3 settings
juju config s3-integrator \
  endpoint=https://s3.amazonaws.com \
  bucket=my-beszel-backups \
  region=us-east-1

# Add credentials
juju run s3-integrator/leader sync-s3-credentials \
  access-key=<your-access-key> \
  secret-key=<your-secret-key>

# Enable backups in Beszel
juju config beszel s3-backup-enabled=true

# Integrate
juju integrate beszel s3-integrator
```

Test the backup:

```bash
juju run beszel/0 backup-now
```

List backups:

```bash
juju run beszel/0 list-backups
```

## Step 8: Configure Alerts

1. Log into Beszel Hub
2. Navigate to Settings → Alerts
3. Configure alert rules:
   - CPU usage > 80%
   - Memory usage > 90%
   - Disk usage > 85%
4. Set up notification channels (email, Slack, etc.)
5. Save configuration

## Step 9: Add More Systems

Repeat Step 5 for each system you want to monitor:

1. Generate a new token
2. Install the agent on the target system
3. Configure the agent with hub URL and token
4. Add the system in the Hub UI

## Troubleshooting

### Beszel Hub Not Starting

Check the logs:

```bash
juju debug-log --include beszel
```

Check storage is attached:

```bash
juju storage
```

### Agent Can't Connect

Verify the hub URL is accessible from the agent system:

```bash
curl -I https://beszel.example.com
```

Check firewall rules allow connections on port 443 (or your configured port).

### Ingress Not Working

Check ingress status:

```bash
juju status nginx-ingress-integrator
kubectl get ingress -n <model-name>
```

Verify DNS points to your ingress controller's external IP.

## Next Steps

- Explore the Beszel Hub dashboard and metrics
- Set up custom dashboards for your infrastructure
- Configure advanced alert rules
- Integrate with your incident management system
- Scale monitoring to additional systems

## Additional Resources

- [Beszel Documentation](https://beszel.dev)
- [Juju Documentation](https://juju.is/docs)
- [Charm README](README.md)
- [Report Issues](https://github.com/tonyandrewmeyer/beszel-k8s-operator/issues)

## Getting Help

If you encounter issues:

1. Check the [troubleshooting section](#troubleshooting) above
2. Review Juju logs: `juju debug-log --include beszel`
3. Check charm status: `juju status beszel --relations`
4. File an issue on GitHub with logs and configuration details
