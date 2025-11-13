<template>
  <div v-on:mouseleave="clean">
    <ImageLayer
      ref="svgImage"
      v-if="parsedElement"
      v-model:scale="scale"
      v-model:position="viewPosition"
      v-model:rotation-angle="rotationAngle"
      :element="parsedElement"
      :class="{ 'drag-cursor': mouseDown }"
      v-on:wheel="e => mouseAction(e, 'zoom')"
      v-on:dblclick="e => mouseAction(e, 'dbClick')"
      v-on:mousedown="e => mouseAction(e, 'down')"
      v-on:mouseup="e => mouseAction(e, 'up')"
      v-on:mousemove="e => mouseAction(e, 'move')"
    >
      <template v-slot:overlay>
        <div class="is-pulled-right tools">
          <!-- Zoom slider -->
          <Slider
            v-on:update:level="updateScale"
            :level="scale.factor"
            :titles="{
              plus: 'Zoom in',
              minus: 'Zoom out',
              input: ZOOM_FACTORS[scale.factor]
            }"
            :max="ZOOM_FACTORS.length - 1"
            :gap="1"
          />
          <!-- Open in new tab button -->
          <a
            class="selectable tool-icon"
            title="Open the full image in another tab"
            :href="sourceImageUrl"
            target="_blank"
          >
            <span>
              <i class="fas fa-external-link-alt"></i>
            </span>
          </a>
          <!-- Rotation buttons -->
          <a
            class="selectable tool-icon"
            title="Rotate image 90° to the left"
            v-on:click="rotationAngle -= 90"
          >
            <span>
              <i class="fas fa-undo-alt"></i>
            </span>
          </a>
          <a
            class="selectable tool-icon"
            title="Rotate image 90° to the right"
            v-on:click="rotationAngle += 90"
          >
            <span>
              <i class="fas fa-redo-alt"></i>
            </span>
          </a>

          <!-- Drawing tools -->
          <template v-if="elementMode === CREATE_MODE">
            <a
              class="selectable tool-icon"
              :class="{ 'selected': tool === RECTANGLE_TOOL }"
              title="Create an element with a rectangle shape"
              v-on:click="changeTool(RECTANGLE_TOOL)"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
                role="img"
                width="1em"
                height="1em"
                preserveAspectRatio="xMidYMid meet"
                viewBox="0 0 512 512"
              >
                <path
                  fill="currentColor"
                  d="M36 416h440a20.023 20.023 0 0 0 20-20V116a20.023 20.023 0 0 0-20-20H36a20.023 20.023 0 0 0-20 20v280a20.023 20.023 0 0 0 20 20Zm12-288h416v256H48Z"
                />
              </svg>
            </a>
            <a
              class="selectable tool-icon"
              :class="{ 'selected': tool === POLYGON_TOOL }"
              title="Create an element with a free polygon shape"
              v-on:click="changeTool(POLYGON_TOOL)"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
                role="img"
                width="1em"
                height="1em"
                preserveAspectRatio="xMidYMid meet"
                viewBox="0 0 100 100"
              >
                <path
                  fill="currentColor"
                  d="M33.162 19.463a3.5 3.5 0 0 0-3.111 1.974L9.34 64.239a3.5 3.5 0 0 0 2.632 4.985l75.015 11.275a3.5 3.5 0 0 0 3.846-4.55L76.566 32.456a3.5 3.5 0 0 0-2.431-2.293l-40.04-10.586a3.5 3.5 0 0 0-.933-.115zm1.934 7.621l35.412 9.361l11.904 36.287l-64.7-9.724l17.384-35.924z"
                  color="currentColor"
                />
              </svg>
            </a>
            <a
              class="selectable tool-icon"
              :class="{ 'selected': tool === EDITION_TOOL }"
              title="Select and edit an existing element"
              v-on:click="changeTool(EDITION_TOOL)"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="1em"
                height="1em"
                preserveAspectRatio="xMidYMid meet"
                viewBox="0 0 24 24"
              >
                <g
                  fill="none"
                  stroke="currentColor"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                >
                  <path
                    d="M20 16V9.5c0-.828-.641-1.5-1.48-1.5C18 8 17 8.3 17 9.5M8 14V5.52M20 16c0 4-3.134 6-7 6s-5.196-1-8.196-6l-1.571-2.605c-.536-.868-.107-1.994.881-2.314a1.657 1.657 0 0 1 1.818.552L8 14.033"
                  /><path d="M14 11V7.5A1.5 1.5 0 0 1 15.5 6v0A1.5 1.5 0 0 1 17 7.5V11m-6 0V6.5A1.5 1.5 0 0 1 12.5 5v0A1.5 1.5 0 0 1 14 6.5V11m-6 0V2.5A1.5 1.5 0 0 1 9.5 1v0A1.5 1.5 0 0 1 11 2.5V11" />
                </g>
              </svg>
            </a>
          </template>
        </div>
      </template>
      <template v-slot:layer>
        <!-- Visible children -->
        <ElementZone
          v-for="child in parsedChildren.filter(child => child)"
          :key="child.id"
          :parent="parsedElement"
          :element="child"
          :class="{ 'hidden': elementMode === CREATE_MODE && tool === EDITION_TOOL && editedElement && editedElement.id === child.id }"
          v-on:select="select(child.id)"
        />
        <svg
          v-bind="originalBoundingBox"
          ref="svgInput"
          :viewBox="elementViewBox"
        />

        <template v-if="elementMode === CREATE_MODE">
          <!--
            This transparent rectangle gets shown whenever we want all mouse events to be captured by
            the ImageLayer event handlers, bypassing all the others: this includes drawing a rectangle
            or polygon, or while dragging an existing polygon around.
          -->
          <rect
            v-if="tool !== EDITION_TOOL"
            v-bind="originalBoundingBox"
            fill="transparent"
          />
          <!-- Display the currently edited element using lines and circles -->
          <g v-if="editedElement" v-on:mouseover="setHoveredElement(editedElement.id)" v-on:mouseleave="setHoveredElement(null)">
            <!-- A polyline for the background color, allowing to drag the element around. -->
            <polyline
              :points="svgPolygon(editedElement.polygon)"
              :fill="INTERACTIVE_POLYGON_COLORS.highlighted"
              fill-opacity="0.5"
              :class="{ 'mouse-cursor': tool === EDITION_TOOL }"
            />
            <!-- Draw lines separately from the polyline; this might later allow dragging lines or creating median points -->
            <line
              v-for="(point, index) in editedElement.polygon.slice(0,-1)"
              :key="'line-' + index"
              :x1="point[0]"
              :y1="point[1]"
              :x2="editedElement.polygon[index + 1][0]"
              :y2="editedElement.polygon[index + 1][1]"
              :stroke="INTERACTIVE_POLYGON_COLORS.highlighted"
              stroke-width="2"
              vector-effect="non-scaling-stroke"
            />
            <!--
              The non-scaling-stroke effect causes the points to keep the same size, no matter the zoom level.
              This is why we use a line here and not a circle; only the stroke can keep its size, not a whole shape.
              A circle's radius would be relative to the element, and re-computing its radius each time
              to fit the whole screen is too complex.
              The line starts and ends at the same point, so all we see is one round stroke linecap.

              We only map the mouse up and down event on this point; the move or wheel events will be captured
              by the ImageLayer. We also do not draw the last point, since it is the same as the first.
            -->
            <line
              v-for="(point, index) in editedElement.polygon.slice(0, -1)"
              :key="'point-' + index"
              :x1="point[0]"
              :y1="point[1]"
              :x2="point[0]"
              :y2="point[1]"
              :stroke="INTERACTIVE_POLYGON_COLORS.highlighted"
              :stroke-width="POINT_DIAMETER"
              stroke-linecap="round"
              vector-effect="non-scaling-stroke"
              v-on:mousedown="pointMouseDown(index)"
              v-on:mouseup="event => pointMouseUp(event, index)"
              :class="{ 'mouse-cursor': tool === EDITION_TOOL }"
            />
          </g>
        </template>
      </template>
    </ImageLayer>
  </div>
</template>

<script>
import { cloneDeep, isEqual } from 'lodash'
import { mapActions, mapMutations, mapState } from 'vuex'
import { ZOOM_FACTORS, INTERACTIVE_POLYGON_COLORS, ELEMENT_MODES, DISPLAY_MODE, CREATE_MODE, RECTANGLE_TOOL, POLYGON_TOOL, EDITION_TOOL } from './js/config'
import { boundingBox, checkPolygon, iiifUri, shiftPolygon, pointsEqual, polygonsEqual, InvalidPolygonError, svgPolygon } from './js/helpers'
import store from './js/store'

import ImageLayer from './vue/ImageLayer.vue'
import Slider from './vue/Slider.vue'
import ElementZone from './vue/ElementZone.vue'

/*
 * Restore the current zoom factor when annotating on a campaign.
 * Zoom factors are stored by campaign, in a JSON format {<campaign_id>: <zoom_factor>}
 */
const LOCAL_STORAGE_ZOOM_FACTORS = 'interactive-image-zoom-factor'

export default {
  store,
  components: {
    ImageLayer,
    ElementZone,
    Slider
  },
  /*
   * We cannot pass an object as a props to a web component.
   * So we receive strings and parse them as data in a watch function
   */
  props: {
    element: {
      type: String,
      default: JSON.stringify(null)
    },
    children: {
      type: String,
      default: JSON.stringify([])
    },
    mode: {
      type: String,
      validator: value => { return ELEMENT_MODES.includes(value) },
      default: DISPLAY_MODE
    },
    campaignId: {
      type: String,
      default: 'default'
    }
  },
  data: () => ({
    POINT_DIAMETER: '15px',
    INTERACTIVE_POLYGON_COLORS,
    CREATE_MODE,
    ZOOM_FACTORS,
    POLYGON_TOOL,
    RECTANGLE_TOOL,
    EDITION_TOOL,
    // Element to display
    parsedElement: null,
    // Children to display as polygons
    parsedChildren: [],
    // Edited element
    editedElement: null,
    // Stores an edited polygon point index
    movedPointIndex: null,
    // Mouse is kept down
    mouseDown: false,
    // Required to compute a relative mouse translation
    lastMousePosition: null,
    // Set to true when the edited polygon has been modified (dragged or distorted)
    updatedPolygon: false,
    /**
     * When an annotation action is cancelled and the mouse was held down,
     * this is set to true to cause the next mouseup event to be ignored.
     * Note that this mouseup can occur anywhere, including outside of the component.
     */
    cancelled: false,
    // Zoom factors stored in local storage
    storedZoomFactors: {},
    /*
     * View scaling
     * Factor represents the zoom percentage index from ZOOM_FACTORS array
     */
    scale: { x: 0, y: 0, factor: 0, applied: true },
    // Image position
    viewPosition: { x: 0, y: 0, applied: false, recenter: true },
    // Drawing mode, rectangle by default
    tool: RECTANGLE_TOOL,
    // Rotation currently applied
    rotationAngle: 0
  }),
  created () {
    this.setElementMode(this.mode)

    this.parsedElement = JSON.parse(this.element)
    this.parsedChildren = JSON.parse(this.children)

    // Apply a scale factor if defined in the local storage
    const value = localStorage.getItem(LOCAL_STORAGE_ZOOM_FACTORS)
    this.storedZoomFactors = value ? JSON.parse(value) : {}
    if (this.campaignZoomFactor !== 0) {
      this.scale = {
        ...this.getChildrenCenter(),
        factor: this.campaignZoomFactor,
        applied: false
      }
    }

    // Custom events to retrieve data from the application
    document.addEventListener('update-props', (evt) => {
      const UPDATE_METHODS = {
        element: (value) => { this.parsedElement = value },
        children: (value) => { this.parsedChildren = value },
        mode: this.setElementMode
      }

      Object.entries(evt.detail).forEach(([key, value]) => {
        if (key in UPDATE_METHODS) UPDATE_METHODS[key](value)
      })
    })

    document.addEventListener('update-highlighted-elements', (evt) => { this.setHighlightedElements({ ids: evt.detail }) })

    document.addEventListener('update-selected-elements', (evt) => {
      const ids = evt.detail
      this.setSelectedElements({ ids, force: true })
      if (!ids.includes(this.editElement?.id)) this.editedElement = null
    })
    document.addEventListener('select-element', (evt) => {
      const id = evt.detail
      this.addSelectedElement({ id, force: true })
      if (this.editedElement?.id !== id) this.editedElement = null
    })
    document.addEventListener('unselect-element', (evt) => {
      const id = evt.detail
      this.removeSelectedElement({ id, force: true })
      if (this.editedElement?.id === id) this.editedElement = null
    })

    document.addEventListener('delete-element', (evt) => {
      const id = evt.detail
      this.removeSelectedElement({ id, force: true })
      this.parsedChildren.splice(this.getChildIndex(id), 1)
      if (this.editedElement?.id === id) this.editedElement = null
    })
  },
  computed: {
    campaignZoomFactor () {
      // Zoom factor for the current campaign
      return parseInt(this.storedZoomFactors[this.campaignId]) || 0
    },
    ...mapState('element', { selectedElements: 'selected', hoveredElement: 'hovered', elementMode: 'mode' }),
    /**
     * Bounding box of the polygon
     */
    originalBoundingBox () {
      if (!this.parsedElement) return {}
      return boundingBox(this.parsedElement)
    },
    elementViewBox () {
      const { x, y, width, height } = this.originalBoundingBox
      return [x, y, width, height].join(' ')
    },
    sourceImageUrl () {
      if (!this.parsedElement) return
      return iiifUri(this.parsedElement)
    }
  },
  methods: {
    ...mapMutations('element', { setSelectedElements: 'setSelected', addSelectedElement: 'addSelected', removeSelectedElement: 'removeSelected', setHighlightedElements: 'setHighlighted', setHoveredElement: 'setHovered' }),

    ...mapActions('element', { setElementMode: 'setMode' }),

    svgPolygon,

    updateScale (factor) {
      this.scale = {
        x: null,
        y: null,
        factor,
        applied: false
      }
    },

    changeTool (tool) {
      // Abort any possible ongoing creation/edition
      this.abort()
      this.tool = tool
    },

    clean () {
      if (!this.mouseDown) return
      // Clean editor when going outside component
      this.mouseDown = false
      this.lastMousePosition = null
      // Trigger a view update translating the image
      if (!this.viewPosition.recenter) this.viewPosition = { ...this.viewPosition, recenter: true }
    },

    elementLimits (position) {
      // Return a position within image limits
      const { x, y, width, height } = this.originalBoundingBox
      let [posX, posY] = position
      if (posX < x) posX = x
      else if (posX > x + width) posX = x + width
      if (posY < y) posY = y
      else if (posY > y + height) posY = y + height
      return [posX, posY]
    },

    getPosition (event) {
      // Returns relative mouse position on a scaled SVG layer
      const svgPoint = this.$refs.svgInput.createSVGPoint()
      Object.assign(svgPoint, { x: event.clientX, y: event.clientY })
      return svgPoint.matrixTransform(this.$refs.svgInput.getScreenCTM().inverse())
    },

    mouseAction (e, action) {
      // Ignore everything but the left mouse button
      if (action === 'down' && e.buttons !== 1) return

      // Nothing to do on a simple mouse move (no dragging)
      if (action === 'move' && (!this.mouseDown && !this.editedElement)) return

      const position = this.getPosition(e)
      if (!position) throw new Error('Mouse position could not be determined on SVG layer.')
      const mouseCoords = [position.x, position.y]

      if (['up', 'down'].includes(action)) {
        this.mouseDown = action === 'down'

        /*
         * When an annotation is cancelled while the user holds the mouse button down,
         * cancelled is set to ignore the next mouseup event.
         * The mouseup event can however occur outside of this component, so it will never
         * be captured here; so if we catch a mousedown event instead, we will also
         * turn off the cancellation flag, without ignoring the event.
         */
        if (this.cancelled) {
          this.cancelled = false
          if (!this.mouseDown) return
        }
      }

      // Update the viewBox on mouseup event if the image has been translated
      if ((this.viewPosition.x || this.viewPosition.y) && !this.viewPosition.recenter && action === 'up') {
        this.viewPosition = { ...this.viewPosition, recenter: true }
        this.lastMousePosition = null
        return
      }

      // Dispatch actions
      if (action === 'zoom') {
        this.zoom(mouseCoords, e)
      } else if (this.elementMode !== CREATE_MODE || e.shiftKey) {
        if (this.mouseDown) this.translate(mouseCoords)
      } else if (this.elementMode === CREATE_MODE) {
        if (this.tool === RECTANGLE_TOOL) this.editRectangle(mouseCoords, action)
        else if (this.tool === POLYGON_TOOL) this.editPolygon(mouseCoords, action)
        else if (this.tool === EDITION_TOOL) this.edit(mouseCoords, action)
      }

      // Set last move position
      if (this.mouseDown && action === 'move') {
        if (this.viewPosition.applied) {
          // Do not store mouse coords right after the CSS translation
          this.lastMousePosition = mouseCoords
        }
        this.viewPosition.applied = true
      } else {
        this.lastMousePosition = null
      }
    },

    getChildIndex (id) {
      return this.parsedChildren.findIndex(element => element?.id === id)
    },

    getChildrenCenter () {
      if (!this.parsedChildren?.length) {
        // By default focus at the center of the image
        const { x, y, width, height } = this.originalBoundingBox
        return { x: Math.ceil(x + width / 2), y: Math.ceil(y + height / 2) }
      }
      const polygons = this.parsedChildren.map(child => child?.polygon || [])
      const pointsX = polygons.flat(1).map(point => point[0])
      const pointsY = polygons.flat(1).map(point => point[1])
      // Compute the center of the bounding box containing all points
      return {
        x: (Math.ceil(Math.min(...pointsX) + Math.max(...pointsX)) / 2),
        y: (Math.ceil(Math.min(...pointsY) + Math.max(...pointsY)) / 2)
      }
    },

    translate (position) {
      if (!this.lastMousePosition) return
      const [dX, dY] = position.map((pt, index) => pt - this.lastMousePosition[index])
      this.viewPosition = {
        x: this.viewPosition.x + dX,
        y: this.viewPosition.y + dY,
        recenter: false,
        applied: false
      }
    },

    zoom (position, event, withLimits = true) {
      if (this.mouseDown) return
      let factor = this.scale.factor + (event.deltaY < 0 ? 1 : -1)
      // Limit zoom factor
      if (factor < 0) factor = 0
      if (factor >= ZOOM_FACTORS.length) factor = ZOOM_FACTORS.length - 1
      // Factor has not been updated
      if (factor === this.scale.factor) return
      const [x, y] = withLimits ? this.elementLimits(position) : { x: position.x, y: position.y }
      if (!this.scale.applied) this.scale = { ...this.scale, factor }
      else this.scale = { x, y, factor, applied: false }
    },

    select (id) {
      // Do not select an element after translating the image
      if (this.viewPosition.x || this.viewPosition.y) return

      // Allow to unselect an element
      const index = this.selectedElements.indexOf(id)
      if (index > -1) this.removeSelectedElement({ id })
      else this.addSelectedElement({ id })
    },

    editElement (element) {
      // Edited element may have a polygon if defined
      if (element !== null && !element.polygon) {
        throw new Error('Edited element must be null or have a defined polygon.')
      }
      this.editedElement = element
    },

    create () {
      if (!this.editedElement) return

      // Check polygon
      let polygon
      try {
        polygon = checkPolygon(this.editedElement.polygon)
        this.editElement({ ...this.editedElement, polygon })
      } catch (e) {
        if (!(e instanceof InvalidPolygonError)) throw e
        this.editElement(null)
        return
      }

      const lastElement = this.parsedChildren[this.parsedChildren.length - 1]
      const newId = lastElement && typeof lastElement.id === 'number' ? lastElement.id + 1 : 1
      const newElement = { id: newId, polygon }
      this.parsedChildren.push(newElement)
      this.editElement(null)

      // Send notification to the application
      document.dispatchEvent(new CustomEvent('create-element', { detail: newElement }))
    },

    editRectangle (position, action) {
      const polygon = this.editedElement && cloneDeep(this.editedElement.polygon)

      if (!polygon && action === 'down') {
        // Create a temporary edited element with all rectangle points
        this.editElement({
          id: 'created-polygon',
          polygon: Array.from({ length: 5 }, () => [...position])
        })
      } else if (this.editedElement && action === 'move') {
        // Move rectangle points depending on mouse pointer position
        const limitedPosition = this.elementLimits(position)
        polygon.splice(2, 1, limitedPosition)
        // Second and third points respectively receive x and y cursor coordinates
        polygon[1][0] = limitedPosition[0]
        polygon[3][1] = limitedPosition[1]
      } else if (this.editedElement && action === 'up') {
        return this.create()
      }

      if (polygon) {
        this.editElement({ ...this.editedElement, polygon })
      }
    },

    editPolygon (position, action) {
      const polygon = this.editedElement && [...this.editedElement.polygon]
      const point = this.elementLimits(position)

      if (action === 'up') {
        // Create a temporary edited element with drawn polygon first and last point
        if (!polygon) {
          this.editElement({ id: 'created-polygon', polygon: [point, point] })
          return
        }
        polygon.push(point)
      } else if (this.editedElement && action === 'move') {
        // Add a segment between the last polygon point and the current cursor position
        polygon.splice(-1, 1, point)
      } else if (this.editedElement && action === 'dbClick') {
        /*
         * Remove the above segment, which was only there only to provide feedback to the user,
         * and replace it with the first point of the polygon to close it.
         */
        polygon.splice(-1, 1, polygon[0])
      }

      // Update the edited element
      if (polygon) {
        this.editElement({ ...this.editedElement, polygon })
      }

      // Trigger element creation on double click, only after updating the selected element
      if (this.editedElement && action === 'dbClick') this.create()
    },

    /**
     * Event handler for the mousedown event on a single point.
     *
     * With the edition tool, this sets movedPointIndex to begin moving a point.
     * With any other tool, we do nothing and let the ImageLayer's mouseup event deal with it.
     *
     * @param {number} index Zero-based index of the point in the polygon.
     */
    pointMouseDown (index) {
      if (this.tool === EDITION_TOOL) this.movedPointIndex = index
    },

    /**
     * Event handler for the mouseup event on a single point.
     *
     * With the polygon tool, a click on the first point should cause the polygon to be closed and created;
     * a click on any other point should do nothing.
     * With any other tool, we do nothing and let the ImageLayer's mouseup event deal with it.
     *
     * @param {MouseEvent} event Mouse event instance.
     * @param {number} index Zero-based index of the point in the polygon.
     */
    pointMouseUp (event, index) {
      // When an annotation action is cancelled, we should ignore the next mouseup event.
      if (this.cancelled) {
        this.cancelled = false
        return
      }
      if (this.tool !== POLYGON_TOOL) return
      /*
       * Ensure clicking on any point with a polygon tool does not cause the ImageLayer's mouseup event to be fired
       * This prevents creating a new polygon right after finishing one.
       */
      event.stopPropagation()
      if (index !== 0) return
      /*
       * When the user moves the mouse around, editPolygon adds a fake point at the end of the polygon;
       * we therefore replace that final point with the first point to properly close the polygon.
       * Merely adding the first point with polygon.push(polygon[0]) would cause an extra point to be
       * present when the element is created.
       */
      const polygon = [...this.editedElement.polygon]
      polygon.splice(-1, 1, polygon[0])
      this.editElement({ ...this.editedElement, polygon })

      // Trigger element creation
      this.create()
    },

    /**
     * Called by the generic edit event handler to handle a mouse move while a point is being dragged.
     * This is not an event handler by itself because this move event cannot be captured on the SVG element of a point,
     * since the mouse might end up moving outside of the point to drag it around.
     * Instead, the original event is captured by the ImageLayer event handlers due to the transparent rectangle.
     * @param {[number, number]} position X,Y coordinates of the mouse on the element.
     * @returns {[number, number][]} An updated polygon.
     */
    movePoint (position) {
      const polygon = [...this.editedElement.polygon]
      const limitedPosition = this.elementLimits(position)

      // Do nothing if the polygon was not updated
      if (pointsEqual(polygon[this.movedPointIndex], limitedPosition)) return

      polygon.splice(this.movedPointIndex, 1, limitedPosition)

      // The first and last points of a polygon are the same; when editing the first point, also edit the last one.
      if (this.movedPointIndex === 0) polygon.splice(-1, 1, limitedPosition)

      return polygon
    },

    /**
     * Called by the generic edit event handler to handle a mouse move while the SVG polyline is being dragged.
     * This is not an event handler by itself because this move event cannot be captured on the polyline,
     * since the mouse might end up moving outside of it to drag it around.
     * @param {[number, number]} position X,Y coordinates of the mouse on the element.
     * @returns {[number, number][]} An updated polygon.
     */
    movePolygon (position) {
      // Ignore any potential 0-pixel moves
      if (pointsEqual(this.lastMousePosition, position)) return

      const polygon = this.editedElement.polygon

      // Compute mouse translation vector relatively to image size
      const translationVector = position.map((pt, index) => pt - this.lastMousePosition[index])
      const newPolygon = shiftPolygon(polygon, translationVector)

      // If the translation results in any of the points being out of bounds, abort
      if (!newPolygon.every(point => pointsEqual(point, this.elementLimits(point)))) return
      return newPolygon
    },

    /**
     * Save the edited element once an update is completed.
     */
    saveEdited () {
      // Reset edition data
      this.movedPointIndex = null
      if (this.lastMousePosition) {
        // Hover edited element again: the transparent layer caused the edited element to no longer be hovered.
        this.setHoveredElement(this.editedElement.id)
      }
      const indexBaseElt = this.getChildIndex(this.editedElement.id)
      const baseElt = this.parsedChildren[indexBaseElt]
      // Do not save an unchanged polygon
      if (baseElt && !this.updatedPolygon) return

      this.updatedPolygon = false
      try {
        const reorderedPolygon = checkPolygon(this.editedElement.polygon)

        // The polygon was unchanged, no patch required!
        if (polygonsEqual(reorderedPolygon, baseElt.polygon)) return

        const updatedElement = { ...this.editedElement, polygon: reorderedPolygon }
        this.parsedChildren[indexBaseElt] = updatedElement

        // Send notification to the application
        document.dispatchEvent(new CustomEvent('update-element', { detail: { id: this.editedElement.id, newPolygon: reorderedPolygon } }))

        this.editElement(null)
      } catch (e) {
        // Cancel polygon update in case of error
        this.edit(baseElt || null)
        throw e
      }
    },

    /**
     * Global mouse event handler for the edition tool.
     * @param {[number, number]} position X,Y coordinates of the mouse on the element.
     * @param {string} action Mouse event name.
     */
    edit (position, action) {
      if (action === 'down') {
        const hoverIndex = this.getChildIndex(this.hoveredElement)
        if (this.hoveredElement && this.parsedChildren[hoverIndex]) this.editElement(this.parsedChildren[hoverIndex])
        else this.editElement(null)
        return
      }

      if (action === 'up') {
        if (this.editedElement) this.saveEdited()
        else this.translate(position)
        return
      }

      if (action !== 'move' || !this.mouseDown) return

      // No edited element: the whole image should be dragged
      if (!this.editedElement) {
        this.translate(position)
        return
      }

      // Defer to the point- or polygon-specific move methods to handle the actual moving
      let polygon = null
      if (this.movedPointIndex !== null) {
        polygon = this.movePoint(position)
      } else if (this.lastMousePosition) {
        polygon = this.movePolygon(position)
      }

      // An API request should be made to update the polygon once the move finishes.
      this.updatedPolygon = true

      // If we got a new polygon, update the element
      if (polygon) {
        this.editElement({ ...this.editedElement, polygon })
      }
    },

    /**
     * Stop any ongoing edition action: drawing a new polygon, moving one, or moving a point.
     */
    abort () {
      if (this.tool === EDITION_TOOL && this.mouseDown && (this.movedPointIndex !== null || this.lastMousePosition)) {
        /*
         * Moving a point or an existing polygon: reset the selected element to the backend data and reset the mouse data
         * If the element cannot be found for any reason, just deselect entirely.
         */
        this.editElement(null)
        this.mouseDown = false
        this.movedPointIndex = null
        this.lastMousePosition = null
        this.updatedPolygon = false
        this.cancelled = true
      } else {
        // Drawing a new polygon: erase the selected element to delete it completely.
        this.editElement(null)
      }
    },

    handleEscape (evt) {
      if (evt.key === 'Escape') {
        this.abort()
      }
    }
  },
  watch: {
    element (newValue, oldValue) {
      if (newValue === oldValue) return
      this.parsedElement = JSON.parse(newValue)
    },
    parsedElement (newValue, oldValue) {
      if (isEqual(newValue, oldValue)) return
      // The element changed but the component was not re-mounted; reset the zoom and position
      this.scale = this.campaignZoomFactor !== 0 ? { ...this.getChildrenCenter(), factor: this.campaignZoomFactor, applied: false } : { x: 0, y: 0, factor: 0, applied: true }
      this.viewPosition = { x: 0, y: 0, applied: true, recenter: false }
    },
    children (newValue, oldValue) {
      if (newValue === oldValue) return
      this.parsedChildren = JSON.parse(newValue)
    },
    mode (newValue, oldValue) {
      if (newValue === oldValue) return
      this.setElementMode(newValue)
    },
    scale (newValue, oldValue) {
      if (newValue === oldValue) return
      /*
       * A computed value is not updated at the same time as the local storage.
       * We have to use a variable to reflect the change.
       */
      this.storedZoomFactors = {
        ...this.storedZoomFactors,
        [this.campaignId]: newValue.factor
      }
      localStorage.setItem(
        LOCAL_STORAGE_ZOOM_FACTORS,
        JSON.stringify(this.storedZoomFactors)
      )
    },
    elementMode (newValue, oldValue) {
      if (newValue === oldValue) return

      if (this.elementMode === CREATE_MODE) {
        document.addEventListener('keyup', this.handleEscape)
      } else {
        document.removeEventListener('keyup', this.handleEscape)
      }
    },
    editedElement (newValue, oldValue) {
      if (newValue?.id === oldValue?.id) return
      // Unselect the previous edited element
      if (oldValue) this.removeSelectedElement({ id: oldValue.id, force: true })
      // Select the new edited element
      if (newValue) this.addSelectedElement({ id: newValue.id, force: true })
    }
  }
}
</script>

<style lang="scss" scoped>

.drag-cursor {
  cursor: grabbing;
}

.tools {
  display: flex;
  flex-direction: column;
  & > a.selectable {
    background: white;
    border-color: #0003;
    color: #363636;
    &.selected {
      background: #209cee;
      color: white;
    }
  }

  & > a.tool-icon {
    display: flex;
    align-items: center;
    padding: 1rem 0;
    border: solid 1px #ccc;
    border-radius: 2px;

    & > svg {
      margin-left: auto;
      margin-right: auto;
      transform: scale(1.5);
    }

    & > span {
      line-height: 0.75rem;
      margin: auto;
    }
  }

  /*
   * The ImageLayer's overlay spans the entire InteractiveImage, so the overlay disables all pointer events on itself
   * so that they can go through it and be handled on the image or polygons.
   * We re-enable them on this component so that the user can interact with either the slider or the image/polygons.
   * Initial patch in Arkindex: https://gitlab.teklia.com/arkindex/frontend/-/merge_requests/1335
   */
  pointer-events: initial;
}

.mouse-cursor:hover {
  cursor: pointer;
}

.hidden {
  display: none;
}
</style>
