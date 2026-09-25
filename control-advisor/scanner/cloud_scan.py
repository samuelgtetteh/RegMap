"""
Cloud resource auditing via the AWS API (boto3) — the cloud equivalent of
network_scan.py. Unlike a network port scan, this doesn't probe open ports on
running machines: it queries the cloud provider's own API to find out what
resources exist and how they're configured (public buckets, wide-open
security groups, over-privileged IAM users), which is how real cloud
security tools (Prowler, ScoutSuite, AWS Config) actually work — cloud
resources are audited through the control plane, not port-scanned.

Points at a real AWS account by default. For local testing against a fake,
disposable AWS environment (see the sibling cloud-target-lab repo, which
runs LocalStack + seeds deliberately-mixed secure/insecure resources), pass
endpoint_url="http://localhost:4566" and dummy credentials — the exact same
boto3 code path is used either way, so nothing here changes when eventually
pointed at a real account.

Output shape matches network_scan.scan() exactly (a "results" list of dicts
with "categories"), so it flows through the existing control_mapper.py /
interview.py / report pipeline completely unchanged. The "ip" field is
reused to hold a resource identifier (e.g. "s3:bucket-name") rather than a
literal IP address — a deliberate reuse of the existing shape, not a new one.
"""
import boto3


def _client(service, endpoint_url, region, access_key, secret_key):
    kwargs = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if access_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client(service, **kwargs)


def _scan_s3(s3):
    results = []
    for bucket in s3.list_buckets().get("Buckets", []):
        name = bucket["Name"]
        is_public = False
        try:
            policy = s3.get_bucket_policy(Bucket=name)["Policy"]
            is_public = '"Principal": "*"' in policy or '"Principal":"*"' in policy
        except Exception:
            pass  # no bucket policy (or couldn't read one) -> treat as not public

        category = "cloud_storage_public" if is_public else "cloud_storage_private"
        results.append({
            "ip": f"s3:{name}",
            "resource_type": "S3 bucket",
            "categories": [category],
        })
    return results


def _scan_security_groups(ec2):
    results = []
    sensitive_ports = {22, 3389, 3306, 5432, 1433}
    for sg in ec2.describe_security_groups().get("SecurityGroups", []):
        exposed = False
        for perm in sg.get("IpPermissions", []):
            from_port = perm.get("FromPort")
            for ip_range in perm.get("IpRanges", []):
                if ip_range.get("CidrIp") == "0.0.0.0/0" and (from_port in sensitive_ports or from_port is None):
                    exposed = True

        category = "cloud_network_exposed" if exposed else "cloud_network_restricted"
        results.append({
            "ip": f"sg:{sg['GroupId']}",
            "resource_type": f"Security group ({sg.get('GroupName', sg['GroupId'])})",
            "categories": [category],
        })
    return results


def _scan_iam(iam):
    results = []
    for user in iam.list_users().get("Users", []):
        username = user["UserName"]
        overprivileged = False
        try:
            for policy_name in iam.list_user_policies(UserName=username).get("PolicyNames", []):
                doc = iam.get_user_policy(UserName=username, PolicyName=policy_name)["PolicyDocument"]
                statements = doc.get("Statement", [])
                if isinstance(statements, dict):
                    statements = [statements]
                for stmt in statements:
                    action = stmt.get("Action")
                    resource = stmt.get("Resource")
                    if stmt.get("Effect") == "Allow" and action == "*" and resource == "*":
                        overprivileged = True
        except Exception:
            pass

        category = "cloud_iam_overprivileged" if overprivileged else "cloud_iam_scoped"
        results.append({
            "ip": f"iam:{username}",
            "resource_type": "IAM user",
            "categories": [category],
        })
    return results


def scan(endpoint_url=None, region="us-east-1", access_key=None, secret_key=None):
    """endpoint_url=None + access_key=None uses boto3's normal credential
    chain against real AWS. Pass endpoint_url + dummy credentials to point at
    a local LocalStack instance instead — see the module docstring."""
    s3 = _client("s3", endpoint_url, region, access_key, secret_key)
    ec2 = _client("ec2", endpoint_url, region, access_key, secret_key)
    iam = _client("iam", endpoint_url, region, access_key, secret_key)

    results = []
    results.extend(_scan_s3(s3))
    results.extend(_scan_security_groups(ec2))
    results.extend(_scan_iam(iam))

    return {
        "cidr": endpoint_url or f"aws:{region}",
        "hosts_scanned": len(results),
        "hosts_found": len(results),
        "duration_seconds": 0,
        "results": results,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Audit AWS (or a LocalStack-simulated AWS) account for security-relevant resource configuration.")
    parser.add_argument("--endpoint-url", default=None, help="e.g. http://localhost:4566 for LocalStack; omit for real AWS")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--access-key", default=None, help="Dummy value works for LocalStack, e.g. 'test'")
    parser.add_argument("--secret-key", default=None)
    args = parser.parse_args()

    report = scan(args.endpoint_url, args.region, args.access_key, args.secret_key)
    print(json.dumps(report, indent=2))
