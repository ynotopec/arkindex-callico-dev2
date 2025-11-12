export const displayConfidenceTag = (field, container) => {
  const confidence = field.getAttribute('confidence')
  if (confidence) {
    const confidenceSpan = document.createElement('span')
    confidenceSpan.classList.add('tag', 'is-light', 'confidence-tag', 'ml-2')
    if (field.hasAttribute('low_confidence')) confidenceSpan.classList.add('is-danger')
    confidenceSpan.setAttribute('title', `${confidence}%`)
    confidenceSpan.textContent = `${parseFloat(confidence).toFixed(0)}%`

    container.appendChild(confidenceSpan)
  }
}
