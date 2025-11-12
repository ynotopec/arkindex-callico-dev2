<template>
  <div class="notification is-danger" v-if="error">
    {{ error }}
  </div>
  <img
    v-else-if="element"
    :style="imageStyle"
    :src="imageUrl"
    v-on:load="onImageLoad"
    v-on:error="onImageError"
    v-on:click="$emit('select')"
  />
  <div v-else class="has-background-grey-lighter"></div>
</template>

<script>
import { mapState, mapActions } from 'vuex'
import { TRANSLATIONS } from '../js/config'
import { iiifUri, boundingBox, checkImageSize, InvalidImageSizeError } from '../js/helpers'

export default {
  emits: ['select', 'loaded'],
  props: {
    elementId: {
      type: String,
      required: true
    },
    height: {
      type: Number,
      default: 0
    },
    width: {
      type: Number,
      default: 0
    },
    imageStyle: {
      type: Object,
      default: () => {}
    }
  },
  data: () => ({
    TRANSLATIONS,
    // Error message to be displayed above the image
    error: ''
  }),
  created () {
    this.getElementDetails()
  },
  computed: {
    ...mapState('element', ['elements']),
    element () {
      return this.elements[this.elementId]
    },
    imageUrl () {
      return iiifUri(this.element, { height: this.height, width: this.width })
    }
  },
  methods: {
    ...mapActions('element', ['get']),
    async getElementDetails () {
      try {
        if (!(this.elementId in this.elements)) await this.get(this.elementId)
        this.$emit('loaded')
      } catch {
        this.error = TRANSLATIONS.elementError
      }
    },
    onImageLoad (event) {
      // Ignore events for images that are no longer displayed
      if (!event.target.isConnected) return

      // Check that the image size is as expected, to detect IIIF server issues
      let width = this.width
      let height = this.height

      const box = boundingBox(this.element)

      // Only one dimension is greater than the image; resize both size parameters before applying it to avoid going over 100% of the image
      if (width > box.width ^ height > box.height) {
        const ratio = Math.max(width / box.width, height / box.height)
        if (width) width = Math.round(width / ratio)
        if (height) height = Math.round(height / ratio)
      }

      // Keep ratio between size parameters
      if (width) height = Math.min(height, box.height, Math.round(width * box.height / box.width))
      if (height) width = Math.min(width, box.width, Math.round(height * box.width / box.height))

      // Set all size parameters
      if (!width) width = Math.max(1, Math.round(height * box.width / box.height))
      if (!height) height = Math.max(1, Math.round(width * box.height / box.width))

      try {
        checkImageSize(event.target, width, height, this.element.image.url)
      } catch (e) {
        if (!(e instanceof InvalidImageSizeError)) throw e
        this.error = e.message
      }
    },
    onImageError (event) {
      // Ignore events for images that are no longer displayed
      if (!event.target.isConnected) return
      this.error = TRANSLATIONS.imageError(this.element.image.url)
    }
  },
  watch: {
    elementId (newValue, oldValue) {
      if (newValue === oldValue) return
      this.error = ''
      this.getElementDetails()
    }
  }
}
</script>

<style scoped>
img {
  height: initial;
  max-width: initial;
}

.has-background-grey-lighter {
  width: 125px;
  height: 150px;
  margin: 0.5rem 0;
}

.notification.is-danger {
  margin: 0.5rem 0;
}
</style>
