<template>
  <div class="is-pulled-right has-text-centered wrapper">
    <span class="is-size-7" v-if="titles.slider">{{ titles.slider }}</span>
    <div class="slider-wrapper">
      <a
        class="has-text-grey-darker mb-1"
        :title="titles.plus"
        v-on:click="update(slideLevel + gap)"
      >
        <span class="icon is-small">
          <i class="fas fa-plus-square"></i>
        </span>
      </a>

      <input
        type="range"
        :min="0"
        :max="max"
        :title="`${titles.input} %`"
        v-model="slideLevel"
        v-on:input="update(slideLevel)"
      />

      <a
        class="has-text-grey-darker mt-1"
        :title="titles.minus"
        v-on:click="update(slideLevel - gap)"
      >
        <span class="icon is-small">
          <i class="fas fa-minus-square"></i>
        </span>
      </a>
    </div>
  </div>
</template>

<script>
export default {
  emits: ['update:level'],
  name: 'SingleSlider',
  props: {
    // Initial level of the slider
    level: {
      type: Number,
      required: true
    },
    /*
     * Title of the slider and buttons
     * { slider, plus, minus, input }
     */
    titles: {
      type: Object,
      required: true
    },
    // Maximum value of the input
    max: {
      type: Number,
      required: true
    },
    // Gap to add/remove when clicking on the buttons
    gap: {
      type: Number,
      required: true
    }
  },
  data: () => ({
    slideLevel: 0
  }),
  methods: {
    update (level) {
      level = Math.min(this.max, Math.max(0, parseInt(level)))
      this.$emit('update:level', level)
    }
  },
  watch: {
    level: {
      immediate: true,
      handler () { this.slideLevel = this.level }
    }
  }
}
</script>

<style scoped lang="scss">
.wrapper {
  background: white;
  border: solid 1px #ccc;
  border-radius: 2px;
}

.slider-wrapper {
  display: flex;
  flex-direction: column;
  text-align: center;
  width: 3rem;
  height: 5.5rem;
  margin: auto;
  & input {
    /*
      Required for Firefox compatibility
      https://developer.mozilla.org/en-US/docs/Web/HTML/Element/input/range#orient_attribute
    */
    transform: rotate(-90deg);
    height: 3rem;
  }
}

span:not(.icon) {
  margin: 0.3rem;
}
</style>
