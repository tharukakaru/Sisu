# Merge of Dev through ed00d15

Combined the production/main history through 84e13f6 with Dev through ed00d15, including the six newer commits for checkout verification, invoice/receipt delivery, owner invitations and SMS MFA, and opt-in unified teacher workspaces.

Conflict decisions:
- Keep the latest Dev owner dashboard/navigation and access-level controls.
- Preserve the signup success heading fix, profile completion popup, explicit dashboard continuation and return-to-sign-in action.
- Route unified teacher accounts through the new workspace service only when its existing configuration flag is enabled. Preserve existing institute-admin and separate teacher onboarding when disabled.
- Rebuild all generated frontend assets from the combined source rather than selecting a branch's compiled output.

Validation: 1,074 backend tests and 198 frontend tests passed; production frontend build passed; static verification passed for 756 Python sources and 138 JSON documents; pip check passed. No production payment, SMS delivery or real account creation was performed.

Deployment: this merge is not deployed. It introduces DocTypes/fields and a pyotp dependency, so the older source-only deployment scripts are not a complete deployment procedure for this release. Production remains at the last operator-confirmed release f013d40 until a separate tested deployment and migration is performed. No production configuration flags were enabled by this merge.
