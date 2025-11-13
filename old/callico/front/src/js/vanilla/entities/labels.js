const ENTITY_TYPE_ATTRIBUTE = 'entity-type'

const _alterLabelBorder = (label, border) => {
  const typeLabel = label.firstElementChild
  typeLabel.style.border = border
}

const _unselectAllLabels = () => {
  SELECTED_LABEL = ''
  document.querySelectorAll('.tags.is-clickable').forEach((label) => {
    // Remove label border
    _alterLabelBorder(label, '')
  })
}

const _selectLabel = (label) => {
  SELECTED_LABEL = label.getAttribute(ENTITY_TYPE_ATTRIBUTE)
  // Restore label border
  _alterLabelBorder(label, '2px solid #333')
}

export const getColor = (label) => {
  const entityType = document.querySelector(`[${ENTITY_TYPE_ATTRIBUTE}="${label}"]`)
  if (!entityType) return DEFAULT_ENTITY_COLOR
  return entityType.getAttribute(ENTITY_COLOR_ATTRIBUTE)
}

const filterEntities = (evt) => {
  const value = evt.target.value
  _unselectAllLabels()
  document.querySelectorAll('.tags.is-clickable').forEach(label => {
    if (label.attributes['entity-type'].value.toLowerCase().includes(value.toLowerCase())) {
      label.style.display = ''
      // Select the first label matching text, if there is one
      if (!SELECTED_LABEL) _selectLabel(label)
    } else {
      label.style.display = 'none'
    }
  })
}

export const initLabels = () => {
  document.querySelectorAll('.tags.is-clickable').forEach(label => {
    label.addEventListener('click', () => {
      _unselectAllLabels()
      _selectLabel(label)
    })
  })

  // Select the first label by default
  const label = document.querySelector('.tags.is-clickable')
  if (!label) return
  label.click()

  const filter = document.getElementById('entityFilter')
  filter.oninput = filterEntities
  filter.parentElement.querySelector('span.is-right').onclick = () => {
    filter.value = ''
    filter.dispatchEvent(new Event('input'))
  }
}

const ENTITY_COLOR_ATTRIBUTE = 'entity-color'
export const DEFAULT_ENTITY_COLOR = '#cfcfcf'

export let SELECTED_LABEL = ''
