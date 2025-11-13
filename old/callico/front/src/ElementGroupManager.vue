<template>
  <div class="is-fullheight">
    <div class="is-flex is-justify-content-space-between">
      <div class="select">
        <select v-model="selectedGroupId" :disabled="!groupsLength">
          <option v-if="!selectedGroupId" value="" disabled>
            ---------
          </option>
          <option v-for="(elements, id) in parsedGroups" :value="id" :key="id">
            {{ getGroupName(id) }}
          </option>
        </select>
      </div>
    </div>

    <div v-if="selectedGroupId" class="has-scrollable-content">
      <span class="subtitle mt-1 mb-1">{{ displayedText }}</span>
      <ul class="has-scrollable-content">
        <li v-for="elementId in selectedGroupElements" :key="elementId">
          <ElementImage
            :element-id="elementId"
            :height="150"
            :width="width"
          />
        </li>
      </ul>
    </div>

    <div v-if="mode === CREATE_MODE" class="is-flex is-justify-content-space-between m-1">
      <button
        type="button"
        class="button is-danger is-light mr-3"
        v-on:click="deleteGroup"
        :disabled="!selectedGroupId"
      >
        {{ capitalize(TRANSLATIONS.delete(typeLowerCase)) }}
      </button>
      <button type="button" class="button is-success is-light" v-on:click="createGroup">
        {{ capitalize(TRANSLATIONS.create(typeLowerCase)) }}
      </button>
    </div>
  </div>
</template>

<script>
import { mapState, mapActions } from 'vuex'
import { capitalize, uniq } from 'lodash'
import { DISPLAY_MODE, CREATE_MODE, TRANSLATIONS } from './js/config'
import { pluralize } from './js/helpers'
import ElementImage from './vue/ElementImage.vue'
import store from './js/store'

export default {
  store,
  components: {
    ElementImage
  },
  /*
   * We cannot pass an object as a props to a web component.
   * So we receive strings and parse them as data in a watch function
   */
  props: {
    groups: {
      type: String,
      default: JSON.stringify([])
    },
    type: {
      type: String,
      default: TRANSLATIONS.element
    },
    mode: {
      type: String,
      default: DISPLAY_MODE,
      validator: (value) => [DISPLAY_MODE, CREATE_MODE].includes(value)
    }
  },
  data: () => ({
    pluralize,
    capitalize,
    CREATE_MODE,
    TRANSLATIONS,
    /*
     * List of grouped elements
     * { [groupId] : [elementId] }
     */
    parsedGroups: {},
    // The selected group to display
    selectedGroupId: ''
  }),
  created () {
    this.parseGroups(JSON.parse(this.groups))
    this.getElementsDetails()
    // Display initial groups
    this.displayGroups()

    // Custom events to retrieve data from the application
    document.addEventListener('update-highlighted-elements', (evt) => {
      /*
       * This event can be sent by the manager directly, we only want to react to it when it
       * is sent by the Vanilla code to reset the `selectedGroupId`.
       */
      const ids = evt.detail
      if (ids && ids.length) return
      this.selectedGroupId = ''
    })
    document.addEventListener('select-element', async (evt) => {
      const id = evt.detail
      if (!(id in this.elements)) await this.get(id)
      if (!this.selectedGroupId) this.createGroup()
      if (this.selectedGroupElements.includes(id)) return
      this.parsedGroups = {
        ...this.parsedGroups,
        [this.selectedGroupId]: [
          ...this.parsedGroups[this.selectedGroupId],
          id
        ]
      }
      this.updateGroup()
    })
    document.addEventListener('unselect-element', (evt) => {
      const id = evt.detail
      /**
       * The element was unselected because it belonged to another group
       * but it was clicked to add it to the current group
       */
      if (!this.selectedGroupElements.includes(id)) {
        document.dispatchEvent(new CustomEvent('select-element', { detail: id }))
      } else {
        const ids = this.selectedGroupElements
        ids.splice(ids.indexOf(id), 1)
        this.parsedGroups = {
          ...this.parsedGroups,
          [this.selectedGroupId]: [...ids]
        }
        this.updateGroup()
      }
    })
    document.addEventListener('update-groups', (evt) => {
      this.parseGroups(evt.detail)
      this.getElementsDetails()
      // Display new groups
      this.displayGroups()
    })
  },
  computed: {
    ...mapState('element', ['elements']),
    typeLowerCase () {
      return this.type.toLowerCase()
    },
    groupsLength () {
      return Object.keys(this.parsedGroups).length
    },
    selectedGroupElements () {
      if (!this.selectedGroupId) return []
      return this.parsedGroups[this.selectedGroupId]
    },
    displayedText () {
      if (!this.selectedGroupElements.length) return this.getGroupName(this.selectedGroupId) + ' ' + TRANSLATIONS.empty

      const selectedInfo = pluralize(TRANSLATIONS.element, this.selectedGroupElements.length)
      return selectedInfo + ' ' + TRANSLATIONS.in + ' ' + this.getGroupName(this.selectedGroupId)
    },
    width () {
      if (!this.$el) return 0
      return this.$el.clientWidth - 10
    }
  },
  methods: {
    ...mapActions('element', ['get']),
    parseGroups (groups) {
      this.parsedGroups = groups.reduce((parsedGroups, group, index) => {
        return {
          ...parsedGroups,
          ...(group ? { [index + 1]: group.elements } : {})
        }
      }, {})
    },
    getGroupName (id) {
      return this.capitalize(this.type) + ' n°' + id
    },
    getElementsDetails () {
      Object.values(this.parsedGroups).forEach(group => {
        group.forEach(elementId => {
          if (elementId in this.elements) return
          this.get(elementId)
        })
      })
    },
    createGroup () {
      let nextId = Object.keys(this.parsedGroups).find(elementId => !this.parsedGroups[elementId].length)
      if (!nextId) {
        // Create a new empty group
        nextId = Math.max(0, ...Object.keys(this.parsedGroups)) + 1
        this.parsedGroups = {
          ...this.parsedGroups,
          [nextId]: []
        }
      }

      this.selectedGroupId = nextId
    },
    updateGroup () {
      document.dispatchEvent(new CustomEvent('update-group', { detail: { id: this.selectedGroupId, elements: this.selectedGroupElements } }))
      document.dispatchEvent(new CustomEvent('update-highlighted-elements', { detail: this.selectedGroupElements }))
      this.displayGroups()
    },
    deleteGroup () {
      if (!this.selectedGroupId) return

      document.dispatchEvent(new CustomEvent('delete-group', { detail: this.selectedGroupId }))

      delete this.parsedGroups[this.selectedGroupId]
      // Reassign the variable to update the computed values
      this.parsedGroups = { ...this.parsedGroups }
      this.selectedGroupId = this.groupsLength ? Math.max(...Object.keys(this.parsedGroups)) : ''

      this.displayGroups()
    },
    displayGroups () {
      // Display groups as selected elements
      document.dispatchEvent(new CustomEvent('update-selected-elements', { detail: uniq(Object.values(this.parsedGroups).flat()) }))
    }
  },
  watch: {
    groups (newValue, oldValue) {
      if (newValue === oldValue) return
      this.selectedGroupId = ''
      this.parseGroups(JSON.parse(newValue))
      this.getElementsDetails()
    },
    selectedGroupId (newValue, oldValue) {
      if (newValue === oldValue) return
      const ids = newValue ? [...this.parsedGroups[newValue]] : []
      document.dispatchEvent(new CustomEvent('update-highlighted-elements', { detail: ids }))
    }
  }
}
</script>

<style lang="scss" scoped>
.is-fullheight {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.is-fullheight .has-scrollable-content {
  margin: 0.5rem 0;
  display: flex;
  flex-direction: column;
  max-height: 100%;
  height: fit-content;
  overflow: auto;
  flex: 1;
}

ul {
  padding: 0;
  list-style: none;
}

button.is-danger[disabled] {
  background-color: #feecf0 !important;
  border-color: #f14668 !important;
}

button.is-success[disabled] {
  background-color: #effaf5 !important;
  border-color: #48c78e !important;
}
</style>
