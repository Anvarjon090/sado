# Support page

The support page puts the monthly development goal, donation amounts, and Ko-fi / PayPal links first. Selecting an amount carries it into PayPal; Ko-fi lets you choose the amount on its own page. No checkout opens until you choose a provider.

Star and community links offer other ways to help. Sponsors remain visible. The Electron page uses the official Sado logo, a single donation panel, visible sponsor and Pro cards, and an icon grid for contact channels. No accordion hides those actions. Controls support keyboard navigation, and decorative interaction animations respect reduced-motion preferences.

Workspace headers link to Support immediately before Search. Workspaces have no sponsor footer; Integrations opens from the sidebar's More fold.

The Support page Pro card opens a dedicated `/pro` page. It leads with $99 per-user yearly, $299 per-user lifetime, and Enterprise contact cards. Pro and Lifetime include user selectors, live totals, and links that preserve the selected plan and quantity on website checkout. The page then shows ten Pro benefits, with commercial production first, followed by recipes, watch folders, batch rules, revision history, delivery packages, project preflight, remote-device compute, remote workers, and encrypted GPU sharing. Core local generation and its AGPL commercial-use rights remain free and unlimited. Licence activation opens from the pricing section. Checkout stays disabled until the paid tools, quantity fulfilment, merchant offer, and terms pass the release gates. Commercial software distribution terms remain a separate agreement. See [the Pro specification](specs/desktop-pro-page.md).

On the Integrations page, only entries with a built-in setup show Works with Sado and capability chips; the rest are marked External link. Setup details and source links are recorded in [the directory notes](integration-directory.md).

License keys require OS-backed encryption; activation fails with a storage error
when the keyring is unavailable or Electron selects plaintext storage. Existing
legacy key files remain readable for deactivation.
