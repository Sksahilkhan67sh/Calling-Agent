export const strings = {
  appName: 'AI Calling Agent',
  skipToContent: 'Skip to content',
  nav: { label: 'Main', campaigns: 'Campaigns', open: 'Open menu', close: 'Close menu' },
  theme: { label: 'Theme', light: 'Light', dark: 'Dark', system: 'System' },
  offline: 'You are offline. Changes cannot be saved until the connection is back.',
  forbidden: {
    title: "You don't have access",
    body: 'Your role does not allow this page. If you think this is a mistake, ask an Admin.',
  },
  notFound: { title: 'Page not found', body: 'The page you asked for does not exist.' },
  error: {
    title: 'Something went wrong',
    body: 'The page failed to load. Reloading usually fixes it.',
    reload: 'Reload page',
  },
  backToCampaigns: 'Back to campaigns',
} as const
