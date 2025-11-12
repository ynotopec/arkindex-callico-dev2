module.exports = {
  // https://vuejs.org/api/compile-time-flags.html#vue-cli
  chainWebpack: (config) => {
    config.plugin('define').tap((definitions) => {
      Object.assign(definitions[0], {
        __VUE_OPTIONS_API__: 'true',
        __VUE_PROD_DEVTOOLS__: 'false',
        __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false'
      })
      return definitions
    })
  },

  // Required to use <template> block in vue components
  runtimeCompiler: true,

  // To generate the callico.css file on development mode too
  css: {
    extract: { ignoreOrder: true }
  },

  // These pages are only used for local demo & development
  pages: {
    index: {
      entry: 'public/index.js',
      template: 'public/index.html',
      title: 'VueJS development'
    },
    'interactive-image-elements': {
      entry: 'public/elements/index.js',
      template: 'public/elements/index.html',
      title: 'InteractiveImage - Elements'
    },
    'group-elements': {
      entry: 'public/group_elements/index.js',
      template: 'public/group_elements/index.html',
      title: 'Group elements'
    }
  }
}
