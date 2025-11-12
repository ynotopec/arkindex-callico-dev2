import * as Sentry from '@sentry/browser'

export const bootSentry = (sentryDsn, env) => {
  Sentry.init({
    dsn: sentryDsn,
    environment: env,

    release: process.env.npm_package_version,
    integrations: [Sentry.browserTracingIntegration()],

    // Log half of the user samples
    tracesSampleRate: 0.5
  })
}
