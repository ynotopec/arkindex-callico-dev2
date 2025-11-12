<template>
  <div v-if="parsedElementIds.length">
    <span class="subtitle">{{ pluralize(typeLowerCase, parsedElementIds.length) }}{{ TRANSLATIONS.colon }}</span>

    <div class="is-flex carousel">
      <button
        class="has-text-grey-darker"
        v-on:click="previous"
      >
        <span class="icon is-large">
          <i class="fas fa-chevron-circle-left fa-2x"></i>
        </span>
      </button>

      <ul ref="list">
        <li
          v-for="(elementId, index) in parsedElementIds"
          :key="elementId"
          ref="items"
        >
          <ElementImage
            :element-id="elementId"
            :height="150"
            :image-style="imageStyle(elementId)"
            v-on:select="setSelected(elementId)"
            v-on:loaded="elementLoaded(elementId, index)"
          />
        </li>
      </ul>

      <button
        class="has-text-grey-darker"
        v-on:click="next"
      >
        <span class="icon is-large">
          <i class="fas fa-chevron-circle-right fa-2x"></i>
        </span>
      </button>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex'
import { DISPLAY_MODE, SELECT_MODE, TRANSLATIONS } from './js/config'
import { pluralize } from './js/helpers'
import ElementImage from './vue/ElementImage.vue'
import store from './js/store'

export default {
  components: {
    ElementImage
  },
  store,
  /*
   * We cannot pass an object as a props to a web component.
   * So we receive strings and parse them as data in a watch function
   */
  props: {
    elementIds: {
      type: String,
      required: true
    },
    type: {
      type: String,
      default: TRANSLATIONS.element
    },
    mode: {
      type: String,
      default: DISPLAY_MODE,
      validator: (value) => [DISPLAY_MODE, SELECT_MODE].includes(value)
    }
  },
  data: () => ({
    pluralize,
    TRANSLATIONS,
    slidesContainer: null,
    // Elements to display
    parsedElementIds: [],
    // Selected element to highlight
    selectedId: null
  }),
  created () {
    this.parsedElementIds = JSON.parse(this.elementIds)

    document.addEventListener('carousel-trigger-selection', (evt) => {
      const id = evt.detail
      this.setSelected(id)
    })
  },
  computed: {
    ...mapState('element', ['elements']),
    typeLowerCase () {
      return this.type.toLowerCase()
    }
  },
  methods: {
    elementLoaded (id, index) {
      if (this.selectedId && this.parsedElementIds.indexOf(this.selectedId) < index) return
      this.setSelected(id)
    },
    setSelected (id) {
      if (this.mode === DISPLAY_MODE || !(id in this.elements) || !this.elements[id].image) return
      this.selectedId = id
      document.dispatchEvent(new CustomEvent('carousel-select-element', { detail: this.elements[this.selectedId] }))
    },
    imageStyle (id) {
      const style = {}
      if (this.mode === SELECT_MODE) style.cursor = 'pointer'
      if (this.selectedId === id) {
        style.border = '2px solid #0087CC'
        style['box-shadow'] = '0 0 10px #0087CC'
      }
      return style
    },
    scrollSize () {
      const widthSlides = this.$refs.items.reduce((sum, item) => sum + item.clientWidth, 0)
      return (widthSlides / this.$refs.items.length) * 2
    },
    previous () {
      this.$refs.list.scrollLeft -= this.scrollSize()
    },
    next () {
      this.$refs.list.scrollLeft += this.scrollSize()
    }
  },
  watch: {
    elementIds (newValue, oldValue) {
      if (newValue === oldValue) return
      this.selectedId = null
      this.parsedElementIds = JSON.parse(newValue)
    }
  }
}
</script>

<style lang="scss" scoped>

.carousel {
  height: 180px;
}

li {
  margin: auto 1rem;
}

ul {
  width: 100%;
  padding: 0;
  margin: 0 1rem;
  display: flex;
  overflow: auto;
  scroll-behavior: smooth;
  list-style: none;
}

.has-background-grey-lighter {
  width: 100px;
  height: 150px;
}

button {
  cursor: pointer;
  background-color: transparent;
  border: none;
  margin: auto;
  opacity: 0.5;
  transition: opacity 100ms;
}

button:hover {
  opacity: 1;
}
</style>
