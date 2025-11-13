export const organizeLeftOrRightFields = (leftFields, rightFields, orSpanContent, previousSibling) => {
  const columns = document.createElement('div')
  columns.classList.add('columns')

  const leftColumn = document.createElement('div')
  leftColumn.classList.add('column')
  leftColumn.appendChild(...leftFields)

  const middleColumn = document.createElement('div')
  middleColumn.classList.add('column', 'is-narrow')
  middleColumn.style.height = middleColumn.style.marginTop = middleColumn.style.marginBottom = 'auto'
  const orSpan = document.createElement('span')
  orSpan.classList.add('has-text-weight-bold')
  orSpan.textContent = orSpanContent
  middleColumn.appendChild(orSpan)

  const rightColumn = document.createElement('div')
  rightColumn.classList.add('column')
  rightColumn.append(...rightFields)

  columns.append(leftColumn, middleColumn, rightColumn)

  previousSibling.parentNode.insertBefore(columns, previousSibling.nextSibling)
}
