const GROUP_ATTRIBUTE = 'group'

export const bootFieldGroups = (container, fieldClass, margin, parentClass = null) => {
  const fields = container.querySelectorAll(fieldClass)

  const groups = {}
  fields.forEach(field => {
    const groupAttribute = field.getAttribute(GROUP_ATTRIBUTE)
    const parentField = parentClass ? field.closest(parentClass) : field

    // Fields without a group should be skipped and left as is
    if (!groupAttribute) return

    /*
     * The first time encountering a group, we need to create a fieldset
     * and insert it in the container
     */
    if (!(groupAttribute in groups)) {
      const groupLegend = document.createElement('legend')
      groupLegend.classList.add('label')
      groupLegend.textContent = groupAttribute

      const group = document.createElement('fieldset')
      group.classList.add('fieldset', margin)
      group.appendChild(groupLegend)

      container.insertBefore(group, parentField)

      groups[groupAttribute] = group
    }

    // Then, we just move the field in the corresponding fieldset
    groups[groupAttribute].appendChild(parentField)
  })
}
