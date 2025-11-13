<template>
  <div :style="imageStyle">
    <div class="notification is-danger" v-if="imageError">
      {{ imageError }}
    </div>
    <div class="image-container is-relative is-flex">
      <div class="is-overlay">
        <slot name="overlay"></slot>
      </div>
      <svg
        :viewBox="viewBox"
        class="has-background-grey-lighter"
        xmlns="http://www.w3.org/2000/svg"
        v-on:wheel.prevent="e => $emit('wheel', e)"
        v-on:mouseup="e => $emit('mouseup', e)"
        v-on:mousemove="e => $emit('mousemove', e)"
      >
        <g :style="scaleStyle">
          <g
            :style="translateStyle"
            v-on:mousedown="e => $emit('mousedown', e) && e.preventDefault()"
            v-on:dblclick="e => $emit('dblclick', e)"
          >
            <!-- Image layer -->
            <image
              v-if="!imageChanged"
              v-bind="elementBBox"
              :href="imageUrl"
              v-on:load="onImageLoad"
              v-on:error="onImageError"
            />
            <slot name="layer" />
          </g>
        </g>
      </svg>
    </div>
  </div>
</template>

<script>
import { isEqual } from 'lodash'
import { IMAGE_QUALITY, ZOOM_FACTORS, IMAGE_TRANSITIONS, NAVIGATION_MARGINS, TRANSLATIONS } from '../js/config'
import { iiifUri, iiifWidth, boundingBox, checkImageSize, InvalidImageSizeError, rotateAround } from '../js/helpers'

export default {
  emits: [
    'wheel',
    'mouseup',
    'mousemove',
    'mousedown',
    'dblclick',
    'update:position',
    'update:scale'
  ],
  props: {
    scale: {
      // Scale factor
      type: Object,
      required: true
    },
    position: {
      // View position in the image
      type: Object,
      required: true
    },
    rotationAngle: {
      type: Number,
      default: 0
    },
    element: {
      type: Object,
      required: true
    }
  },
  data: () => ({
    viewSize: {
      x: 0,
      y: 0,
      width: 0,
      height: 0
    },
    // Do not use animated translation
    translateAnimation: false,
    // Last applied factor
    lastFactor: 100,
    // An error message to be displayed above the image
    imageError: '',
    // Force the image to reload
    imageChanged: false
  }),
  computed: {
    imageStyle () {
      const height = this.imageError ? 'calc(100%  - 3rem)' : '100%'
      return { height, 'min-height': '20rem' }
    },
    imageUrl () {
      return iiifUri(this.element, { width: iiifWidth(IMAGE_QUALITY * 2 / 3) })
    },
    scaleStyle () {
      if (this.scale.applied) return
      return {
        transform: `scale(${this.scaleFactor()})`,
        'transform-origin': `${parseInt(this.zoomFocus.x)}px ${parseInt(this.zoomFocus.y)}px`,
        transition: `transform ${IMAGE_TRANSITIONS}ms ease`
      }
    },
    translateStyle () {
      const style = {
        transform: '',
        'transform-origin': this.center.map(coord => `${coord}px`).join(' '),
        transition: this.translateAnimation ? `transform ${IMAGE_TRANSITIONS}ms ease` : 'none'
      }
      if (this.rotationAngle) style.transform += ` rotate(${this.rotationAngle}deg)`
      style.transform += ` translate(${parseInt(this.position.x)}px,${parseInt(this.position.y)}px)`
      return style
    },
    elementBBox () {
      return boundingBox(this.element)
    },
    // Center point of the element's bounding box
    center () {
      return [
        Math.floor(this.elementBBox.x + this.elementBBox.width / 2),
        Math.floor(this.elementBBox.y + this.elementBBox.height / 2)
      ]
    },
    rotatedBBox () {
      const { x, y, width, height } = this.elementBBox
      // Build a fake polygon from the bounding box
      let polygon = [
        [x, y],
        [x, y + height],
        [x + width, y + height],
        [x + width, y]
      ]
      // Apply rotation
      if (this.rotationAngle) polygon = polygon.map(point => rotateAround(point, this.center, this.rotationAngle))

      /*
       * When rotating the polygon, it is possible to get bounding boxes that go beyond the image or
       * have negative coordinates, so we do not lock to the image's bounds.
       */
      return boundingBox({ polygon }, { imageBounds: false })
    },
    zoomFocus () {
      // Use view center in case zoom focus is not defined
      const { x, y, width, height } = this.viewSize
      return {
        x: this.scale.x !== null ? this.scale.x : x + width / 2,
        y: this.scale.y !== null ? this.scale.y : y + height / 2
      }
    },
    viewBox () {
      const { x, y, width, height } = this.viewSize
      return [x, y, width, height].join(' ')
    },
    marginsMax () {
      // Maximum size allowed for margins as a percent of Max(width, height)
      return Math.max(this.rotatedBBox.width, this.rotatedBBox.height) * NAVIGATION_MARGINS / 100
    }
  },
  methods: {
    getMargins () {
      let [rotatedX, rotatedY] = [this.position.x, this.position.y]
      if (this.rotationAngle) {
        [rotatedX, rotatedY] = rotateAround(
          [this.position.x, this.position.y],
          [0, 0],
          this.rotationAngle
        )
      }
      // Compute actual margins between the view and image coords
      const { x, y, width, height } = this.viewSize
      const left = this.rotatedBBox.x + rotatedX - x
      const right = width - left - this.rotatedBBox.width
      const top = this.rotatedBBox.y + rotatedY - y
      const bottom = height - top - this.rotatedBBox.height
      return { left, right, top, bottom }
    },
    recenter () {
      // Limit maximal image translation as a percentage of the retrieved IIIF image width
      const margins = this.getMargins()
      const max = this.marginsMax
      let [x, y] = [0, 0]

      if (margins.left > max) {
        x = max - margins.left
      } else if (margins.right > max) {
        x = margins.right - max
      }
      if (margins.top > max) {
        y = max - margins.top
      } else if (margins.bottom > max) {
        y = margins.bottom - max
      }
      const recentered = x || y

      // Add the current rotated position before translating
      let [rotatedX, rotatedY] = [this.position.x, this.position.y]
      if (this.rotationAngle) {
        [rotatedX, rotatedY] = rotateAround(
          [this.position.x, this.position.y],
          [0, 0],
          this.rotationAngle
        )
      }
      x += rotatedX
      y += rotatedY

      // Image does not require to be recentered, end here
      if (!recentered) return this.translate({ x, y })

      /**
       * "Unrotate" the final translation vector;
       * the CSS `translate` (controlled by `this.position`) is rotation-unaware,
       * but the SVG viewBox (controlled by `this.viewSize` via `this.translate()`) is rotation-aware.
       */
      let [unrotatedX, unrotatedY] = [x, y]
      if (this.rotationAngle) [unrotatedX, unrotatedY] = rotateAround([x, y], [0, 0], -this.rotationAngle)

      this.translateAnimation = true
      this.$emit('update:position', { x: unrotatedX, y: unrotatedY, applied: false, recenter: false })
      // Recenter and update the view after the animation
      setTimeout(() => {
        this.translateAnimation = false
        this.translate({ x, y })
      }, IMAGE_TRANSITIONS)
    },
    scaleFactor (newFactorIndex = this.scale.factor) {
      // Returns the factor of the applied scaling
      if (this.scale.applied) return 1
      return ZOOM_FACTORS[newFactorIndex] / this.lastFactor
    },
    zoom () {
      // Allow updates during the transition
      const updatedValue = this.scale

      let { x, y, width, height } = this.viewSize

      // Determine zoom focus relative position
      const [focusRatioX, focusRatioY] = [
        (this.zoomFocus.x - x) / width,
        (this.zoomFocus.y - y) / height
      ]

      // Resize the viewBox
      const scaleFactor = this.scaleFactor(updatedValue.factor)
      width /= scaleFactor
      height /= scaleFactor
      x = this.zoomFocus.x - focusRatioX * width
      y = this.zoomFocus.y - focusRatioY * height

      // Update the view after the animation
      setTimeout(() => {
        if (updatedValue !== this.scale) return
        this.$emit('update:scale', { ...this.scale, applied: true })
        this.viewSize = { x, y, width, height }
        // Store last applied factor
        this.lastFactor = ZOOM_FACTORS[updatedValue.factor]
        // Center image if required
        this.recenter()
      }, IMAGE_TRANSITIONS)
    },
    translate (vector) {
      if (!vector) return
      this.viewSize = {
        ...this.viewSize,
        x: this.viewSize.x - vector.x,
        y: this.viewSize.y - vector.y
      }
      this.$emit('update:position', { x: 0, y: 0, applied: true, recenter: false })
    },
    onImageLoad (event) {
      // Ignore events for images that are no longer displayed
      if (!event.target.isConnected) return

      // Check that the image size is as expected, to detect IIIF server issues
      const expectedWidth = Math.min(this.elementBBox.width, iiifWidth(IMAGE_QUALITY * 2 / 3))
      const expectedHeight = Math.trunc(this.elementBBox.height * (expectedWidth / this.elementBBox.width))

      /*
       * An <img> HTML tag has attributes that make it easy to retrieve the original image's size,
       * but the SVG <image> tags do not. Therefore, we create a 'virtual' img tag, assign it the image tag's href,
       * and let the browser be clever enough to not load the same image twice.
       *
       * In Firefox, the image is loaded almost instantaneously; however, in Chromium, it will trigger the normal
       * requests, causing the image to be downloaded twice if the cache is disabled in the developer tools.
       * Not waiting for the image to load causes the size warning to be displayed with an actual image of 0×0px.
       */
      const img = new Image()

      img.addEventListener('load', () => {
        try {
          checkImageSize(img, expectedWidth, expectedHeight, this.element.image.url)
        } catch (e) {
          if (!(e instanceof InvalidImageSizeError)) throw e
          this.imageError = e.message
        }
      }, { once: true })

      img.src = this.imageUrl
    },
    onImageError (event) {
      // Ignore events for images that are no longer displayed
      if (!event.target.isConnected) return
      this.imageError = TRANSLATIONS.imageError(this.element.image.url)
    }
  },
  watch: {
    scale () {
      if (this.scale.applied) return
      this.zoom()
    },
    position (position) {
      if (!position.recenter) return
      this.recenter()
    },
    element (newValue, oldValue) {
      // If the element changes, it means we switched to another element without re-mounting: reset the zoom factor to the initial value
      if (isEqual(newValue, oldValue)) return
      this.lastFactor = 100
    },
    imageUrl () {
      // Reset image error messages if the image changes
      this.imageError = ''

      // Force the image to reload so that the old one is no longer displayed even if the new one has not yet loaded
      this.imageChanged = true
      this.$nextTick(() => { this.imageChanged = false })
    },
    'image.status': {
      handler (newValue) {
        if (newValue === 'error') this.imageError = `The API reports issues with this image from the IIIF server at ${this.element.image.url}. Navigation may have unexpected behavior.`
        else this.imageError = ''
      },
      immediate: true
    },
    /*
     * When loading an element, the viewSize is set by default to the whole element.
     * When the user switches to another element in a way causing the router to reuse components,
     * the bounding box will be updated since the main element changes; we reset the viewSize again.
     */
    elementBBox: {
      handler (newValue) {
        this.viewSize = { ...newValue }
        /*
         * Apply the zoom if a zoom factor is initially set.
         * This cannot be done in the scale watcher as viewSize
         * is not yet defined, causing a zero division error
         */
        if (!this.scale.applied) this.zoom()
      },
      immediate: true
    }
  }
}
</script>

<style scoped lang="scss">
svg {
  flex: 1;
  /*
   * This width is required to avoid issues with Chrome-based browsers:
   * for elements whose bounding box is wider than it is high (e.g. text lines, or landscape pages),
   * the height: 100% defined by .image-container will take precedence over the width.
   * The SVG tag will fill the whole .image-container, so it fills the whole height and does not
   * stop at a maximum width of 100%, even with an explicit max-width: 100%, which overflows
   * the browser's viewport.
   * Removing height: 100% on the .image-container avoids overflowing the viewport, but also means
   * that the SVG element does not fill the page vertically, which makes annotations on those wide
   * but thin elements much more annoying.
   * Setting the width to 0, a valid value which should cause the SVG tag to be completely invisible,
   * instead causes it to behave properly, never resizing itself to exceed a 100% width or height.
   * This makes no difference in Firefox.  `width: inherit` also works, and `width: 100px` causes the
   * SVG to instead have a minimum width of 100 pixels, but still able to expand to fill the flexbox
   * column's width.
   */
  width: 0;
}

.image-container {
  height: 100%;
  width: 100%;
}

.is-overlay {
  pointer-events: none;
  & > * {
    pointer-events: all;
    &:not(:last-child) {
      margin-left: 0.5rem;
    }
  }
}
</style>
