import { createStore } from 'vuex'

/*
 * Store module names. Those must match file names in the js/store folder (e.g. auth → ./auth.js)
 * This is used in place of the typical imports to provide module introspection and hot reloading.
 */
const moduleNames = [
  'element'
]

export const actions = {
  reset ({ commit }, { exclude = [] }) {
    for (const name of moduleNames) {
      if (exclude.includes(name)) continue
      commit(`${name}/reset`)
    }
  }
}

/*
 * The store hot reloading setup: A complex mix of webpack's Hot Module Replacement API and Vuex's hotUpdate.
 *
 * We use `require.context` to properly support hot reloading with dynamic imports (imports with non-constant paths).
 * The `contextId` is used because a new context has to be used on each reload,
 * and the module needs to accept reloads again on the new context.
 *
 * In a production build, this whole process will be evaluated at build time,
 * and nothing of this dynamic loading will be included in the minified bundle.
 *
 * About require.context: https://webpack.js.org/guides/dependency-management/
 * About Webpack's hot reloading API: https://webpack.js.org/api/hot-module-replacement/
 * About Vuex hot reloading: https://vuex.vuejs.org/guide/hot-reload.html
 */
let contextId = null
export const loadModules = () => {
  // Create a new context module to import store modules
  const requireModule = require.context('.', false, /\.js$/)
  // Store the ID for `module.hot.accept`
  contextId = requireModule.id
  // Import modules from their JS files and build the store's modules object
  return moduleNames.reduce((modules, name) => {
    modules[name] = requireModule(`./${name}.js`).default
    return modules
  }, {})
}

const store = createStore({
  actions,
  modules: loadModules(),
  strict: process.env.NODE_ENV === 'development'
})
export default store

if (module.hot) {
  module.hot.accept(contextId, () => {
    store.hotUpdate({
      modules: loadModules()
    })
  })
}
