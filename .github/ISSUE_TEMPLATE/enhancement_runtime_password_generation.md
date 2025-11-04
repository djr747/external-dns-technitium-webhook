## Overview
Implement runtime password generation and expand CI workflow.

## Problem
Currently, fixed or hardcoded passwords are used. This creates potential security risks and lacks runtime flexibility.

## Solution
1. **Random Password Generation:**
   - Generate random, secure passwords at runtime for both the admin and test user accounts.
   - Use robust password policies to ensure high entropy.
   - Generate new passwords for every test run to maintain security during CI operations.

2. **CI Workflow Update:**
   - Extend the CI workflow to include tests for the following:
     - Create, update, and delete operations for all supported record types.
     - Validate password authentication for the admin and test accounts.

## Expected Impact
- Improved runtime security by eliminating hardcoded passwords.
- Expanded integration test coverage ensures robustness across record types.
- Allows authentication mechanisms to be tested dynamically and securely.

## Testing Requirements
- [ ] Verify runtime password generation aligns with the password policy.
- [ ] Ensure CI workflow runs all CRUD operations on supported record types.
- [ ] Validate compatibility with existing deployments and workflows.
- [ ] Maintain 100% test coverage.

## Effort
Estimated: 2 hours

## Additional Context
Integrating this feature will lay groundwork for future runtime-based security enhancements.