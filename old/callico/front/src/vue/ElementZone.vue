<template>
  <polygon
    v-bind="svgProps"
    v-on:mouseover="!isHovered && setHovered(element.id)"
    v-on:mouseleave="setHovered(null)"
    v-on:mouseup.left="$emit('select')"
  >
    <title>{{ element.name || `Element ${element.id}` }}</title>
  </polygon>
</template>

<script>
import { mapState, mapMutations } from 'vuex'
import { svgPolygon } from '../js/helpers'
import { INTERACTIVE_POLYGON_COLORS, SELECT_MODE } from '../js/config'
export default {
  emits: ['select'],
  props: {
    parent: {
      type: Object,
      required: true
    },
    element: {
      type: Object,
      required: true
    }
  },
  computed: {
    ...mapState('element', ['mode', 'selected', 'highlighted', 'hovered']),
    isHighlighted () {
      return this.highlighted && this.highlighted.includes(this.element.id)
    },
    isSelected () {
      return !this.isHighlighted && this.selected && this.selected.includes(this.element.id)
    },
    isHovered () {
      return !this.isSelected && this.hovered && this.hovered === this.element.id
    },
    color () {
      // Return the element color
      if (this.isHighlighted) return INTERACTIVE_POLYGON_COLORS.highlighted
      if (this.isSelected) return INTERACTIVE_POLYGON_COLORS.selected
      return INTERACTIVE_POLYGON_COLORS.visible
    },
    focused () {
      // Use CSS focusing on highlight, select and hover
      return this.isHovered || this.isSelected || this.isHighlighted
    },
    svgProps () {
      if (!this.element) return {}
      return {
        points: this.svgPolygon(this.element.polygon),
        stroke: this.color,
        fill: this.color,
        cursor: this.mode === SELECT_MODE ? 'pointer' : 'default',
        'stroke-opacity': 1,
        'fill-opacity': this.focused ? 0.5 : 0.2,
        'stroke-width': this.focused ? 2 : 1,
        'vector-effect': 'non-scaling-stroke'
      }
    }
  },
  methods: {
    svgPolygon,
    ...mapMutations('element', ['setHovered'])

  }
}
</script>
