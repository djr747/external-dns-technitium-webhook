## Description
<!-- Provide a clear and concise description of your changes -->

## Related Issue
<!-- Link to the issue this PR addresses -->
Fixes #<!-- issue number -->

## Type of Change
<!-- Mark the relevant option with an 'x' -->
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code refactoring
- [ ] Performance improvement
- [ ] Security fix

## Changes Made
<!-- List the specific changes in this PR -->
- 
- 
- 

## Testing
<!-- Describe the tests you ran to verify your changes -->
- [ ] All existing tests pass (`make test`)
- [ ] Added new tests for new functionality
- [ ] Tested manually with ExternalDNS and Technitium DNS
- [ ] Tested in Kubernetes environment

### Test Configuration
<!-- If applicable, describe your test setup -->
```yaml
# Test environment details
```

## Code Quality Checklist
<!-- Ensure all checks pass before requesting review -->
- [ ] Code follows project style guidelines (`make format`)
- [ ] Linting passes (`make lint`)
- [ ] Type checking passes (`make type-check`)
- [ ] Security scans pass (`make security`)
- [ ] All tests pass (`make test`)
- [ ] Code coverage maintained or improved (`make test-cov`)

## Documentation
<!-- Have you updated relevant documentation? -->
- [ ] Updated README.md (if applicable)
- [ ] Updated docs/ files (if applicable)
- [ ] Updated CHANGELOG.md following [Keep a Changelog](https://keepachangelog.com/)
- [ ] Added/updated docstrings for new functions/classes
- [ ] Updated API documentation (if API changes made)

## ExternalDNS Compatibility
<!-- Confirm compatibility with ExternalDNS protocol -->
- [ ] Maintains backward compatibility with ExternalDNS webhook protocol
- [ ] Custom media type preserved: `application/external.dns.webhook+json;version=1`
- [ ] All required endpoints functional: `/health`, `/`, `/records`, `/adjustendpoints`

## Security Considerations
<!-- Have you considered security implications? -->
- [ ] No passwords or tokens logged
- [ ] Error messages sanitized (no sensitive information disclosure)
- [ ] Input validation implemented
- [ ] No new dependencies with known CVEs
- [ ] Follows least privilege principle

## Performance Impact
<!-- Does this change affect performance? -->
- [ ] No significant performance impact
- [ ] Performance improved
- [ ] Performance impact assessed and documented

## Breaking Changes
<!-- If this is a breaking change, describe migration path -->
<!-- What do users need to change? Provide before/after examples -->

## Screenshots/Logs
<!-- If applicable, add screenshots or log output showing the changes -->

## Deployment Notes
<!-- Special instructions for deploying this change -->
- [ ] No special deployment steps required
- [ ] Requires environment variable changes (document below)
- [ ] Requires configuration changes (document below)
- [ ] Requires Technitium DNS version update

## Additional Context
<!-- Any other information reviewers should know -->

---

## Reviewer Checklist
<!-- For maintainers reviewing this PR -->
- [ ] Code quality meets project standards
- [ ] Tests are comprehensive and pass
- [ ] Documentation is clear and complete
- [ ] Security considerations addressed
- [ ] Performance impact acceptable
- [ ] ExternalDNS compatibility maintained
- [ ] CHANGELOG.md updated appropriately
