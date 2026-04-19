// ===== MOCK DATA (matches src/prior_auth_bot/models.py schemas) =====

const MOCK_TRANSCRIPT = `Dr. Smith: Good morning, John. I've reviewed your MRI results from last month. The imaging confirms a complete ACL tear in your left knee.

Patient: That's what I was afraid of. The physical therapy hasn't really helped much over these past three months.

Dr. Smith: Right, we've documented twelve weeks of conservative treatment — physical therapy twice weekly since January. Given the lack of improvement and the complete tear, I'm recommending ACL reconstruction surgery. I'll need to submit a prior authorization to your insurance, Aetna, policy number AET-1234567.

Patient: How long will that take?

Dr. Smith: With our new system, we should have a response within 24 hours.`;

const MOCK_ENTITIES = [
  { name: 'ACL Reconstruction', type: 'procedure', code: 'SNOMED 239165003' },
  { name: 'Physical Therapy', type: 'procedure', code: 'SNOMED 91251008' },
  { name: 'Aetna', type: 'insurance', code: 'Payer ID: AET' },
  { name: 'MRI Knee (Left)', type: 'history', code: 'SNOMED 241601008' },
  { name: 'Ibuprofen 800mg', type: 'medication', code: 'RxNorm 197806' },
];

const MOCK_PA_RESULTS = [
  {
    treatment: 'ACL Reconstruction Surgery',
    requires_pa: true,
    reason: 'Surgical procedure requiring pre-authorization with documentation of failed conservative treatment',
  },
  {
    treatment: 'Physical Therapy (24 sessions)',
    requires_pa: true,
    reason: 'Extended therapy plan exceeding 12-session threshold requires session count approval',
  },
];

const MOCK_FORM = {
  name: 'Aetna Surgical Pre-Authorization Form',
  field_count: 42,
  field_types: '28 Text, 10 CheckBox, 4 RadioButton',
  provider: 'Aetna',
};

const MOCK_MEMORY = {
  memory_type: 'treatment_provider',
  treatment: 'ACL reconstruction',
  provider: 'Aetna',
  advice: 'Include MRI report date and radiologist name. Aetna requires explicit documentation of failed conservative treatment duration (minimum 6 weeks). Include PT session count and date range.',
  success_count: 5,
  relevance_score: 0.94,
  outcome: 'approved',
  tags: ['orthopedic', 'surgical', 'conservative-treatment-required'],
};

const MOCK_POPULATION = {
  total_fields: 42,
  filled_fields: 40,
  skipped_fields: 2,
  llm_attempts: 1,
};

const MOCK_SUBMISSION = {
  delivery_method: 'portal',
  status: 'pending_insurer_review',
  submission_id: 'SUB-2026-0419-001',
};

// Step timing (ms): [processing_time, reveal_time]
const STEP_TIMING = [
  [1500, 0],     // step 0: audio playback
  [2000, 1200],  // step 1: transcription + typewriter
  [1800, 800],   // step 2: entity extraction + highlights
  [1500, 600],   // step 3: PA determination
  [1200, 400],   // step 4: form selection
  [1500, 600],   // step 5: memory retrieval
  [2000, 1000],  // step 6: form population
  [1200, 400],   // step 7: submission
];

// ===== PIPELINE DEMO CLASS =====

class PipelineDemo {
  constructor() {
    this.currentStep = 0;
    this.isRunning = false;
    this.timers = [];
    this.btn = document.getElementById('demo-start-btn');
    this.waveform = document.getElementById('demo-waveform');
    this.pipeFill = document.getElementById('demo-pipe-fill');
    this.outputContent = document.getElementById('demo-output-content');
    this.outputPlaceholder = document.getElementById('demo-output-placeholder');

    if (this.btn) {
      this.btn.addEventListener('click', () => this.start());
    }
  }

  start() {
    if (this.isRunning) return;
    this.reset();
    this.isRunning = true;
    this.btn.disabled = true;
    this.btn.textContent = 'Processing...';
    this.outputPlaceholder.style.display = 'none';
    this.outputContent.classList.add('visible');

    // Start audio animation
    this.waveform.classList.add('playing');

    this.scheduleStep(1, STEP_TIMING[0][0]);
  }

  reset() {
    this.timers.forEach(t => clearTimeout(t));
    this.timers = [];
    this.currentStep = 0;
    this.isRunning = false;

    if (this.btn) {
      this.btn.disabled = false;
      this.btn.innerHTML = `<svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor"><polygon points="4,2 18,10 4,18"/></svg> Process Recording`;
    }

    if (this.waveform) this.waveform.classList.remove('playing');
    if (this.pipeFill) this.pipeFill.style.width = '0%';
    if (this.outputContent) {
      this.outputContent.innerHTML = '';
      this.outputContent.classList.remove('visible');
    }
    if (this.outputPlaceholder) this.outputPlaceholder.style.display = 'flex';

    for (let i = 1; i <= 7; i++) {
      const el = document.getElementById(`demo-step-${i}`);
      if (el) {
        el.classList.remove('active', 'complete');
      }
    }
  }

  scheduleStep(step, delay) {
    const t = setTimeout(() => this.runStep(step), delay);
    this.timers.push(t);
  }

  runStep(step) {
    if (!this.isRunning) return;
    this.currentStep = step;

    // Stop audio after step 1 starts
    if (step >= 1) {
      this.waveform.classList.remove('playing');
    }

    // Activate step indicator
    const stepEl = document.getElementById(`demo-step-${step}`);
    if (stepEl) stepEl.classList.add('active');

    // Update pipe fill
    this.pipeFill.style.width = `${((step - 0.5) / 7) * 100}%`;

    // Schedule completion
    const t = setTimeout(() => this.completeStep(step), STEP_TIMING[step][0]);
    this.timers.push(t);
  }

  completeStep(step) {
    if (!this.isRunning) return;

    const stepEl = document.getElementById(`demo-step-${step}`);
    if (stepEl) {
      stepEl.classList.remove('active');
      stepEl.classList.add('complete');
    }

    this.pipeFill.style.width = `${(step / 7) * 100}%`;

    // Render output
    this.renderStepOutput(step);

    // Schedule next step
    if (step < 7) {
      this.scheduleStep(step + 1, STEP_TIMING[step][1] + 300);
    } else {
      // Done
      const t = setTimeout(() => {
        this.isRunning = false;
        this.btn.disabled = false;
        this.btn.innerHTML = `<svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor"><path d="M4 4h4v12H4zM12 4h4v12h-4z"/></svg> Run Again`;
      }, 1000);
      this.timers.push(t);
    }
  }

  renderStepOutput(step) {
    const entry = document.createElement('div');
    entry.className = 'demo-output-entry';

    switch (step) {
      case 1:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">01</span>
            <span class="demo-entry-title">Transcription Complete</span>
          </div>
          <div class="demo-entry-body">
            <div class="typewriter-text" id="typewriter-target"></div>
          </div>`;
        this.outputContent.appendChild(entry);
        this.typewriterEffect(
          document.getElementById('typewriter-target'),
          MOCK_TRANSCRIPT.substring(0, 200) + '...',
          12
        );
        break;

      case 2:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">02</span>
            <span class="demo-entry-title">Entities Extracted</span>
          </div>
          <div class="demo-entry-body" id="entities-container"></div>`;
        this.outputContent.appendChild(entry);
        this.renderEntities();
        break;

      case 3:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">03</span>
            <span class="demo-entry-title">PA Requirements Determined</span>
          </div>
          <div class="demo-entry-body">
            ${MOCK_PA_RESULTS.map(r => `
              <div class="pa-result">
                <div class="pa-dot ${r.requires_pa ? 'required' : 'not-required'}"></div>
                <div>
                  <div class="pa-treatment">${r.treatment}</div>
                  <div class="pa-reason">${r.reason}</div>
                </div>
              </div>
            `).join('')}
          </div>`;
        this.outputContent.appendChild(entry);
        break;

      case 4:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">04</span>
            <span class="demo-entry-title">Form Selected</span>
          </div>
          <div class="demo-entry-body">
            <div style="display:flex;align-items:center;gap:10px">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="${getComputedStyle(document.documentElement).getPropertyValue('--pi-blue').trim()}" stroke-width="1.5">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <div>
                <div style="font-weight:500;color:var(--pi-text)">${MOCK_FORM.name}</div>
                <div style="font-size:0.85em;color:var(--pi-muted)">${MOCK_FORM.field_count} fields (${MOCK_FORM.field_types})</div>
              </div>
            </div>
          </div>`;
        this.outputContent.appendChild(entry);
        break;

      case 5:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">05</span>
            <span class="demo-entry-title">Memory Retrieved</span>
          </div>
          <div class="demo-entry-body">
            <div class="memory-output-card">
              <div class="memory-output-type">${MOCK_MEMORY.memory_type}</div>
              <div class="memory-output-advice">"${MOCK_MEMORY.advice}"</div>
              <div class="memory-output-meta">
                <span>Relevance: ${(MOCK_MEMORY.relevance_score * 100).toFixed(0)}%</span>
                <span>Success: ${MOCK_MEMORY.success_count}x</span>
                <span>Outcome: ${MOCK_MEMORY.outcome}</span>
              </div>
            </div>
          </div>`;
        this.outputContent.appendChild(entry);
        break;

      case 6:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">06</span>
            <span class="demo-entry-title">Form Populated</span>
          </div>
          <div class="demo-entry-body">
            <div class="form-fill-counter">
              <span class="form-fill-num" id="fill-counter">0</span>
              <span class="form-fill-total">/ ${MOCK_POPULATION.total_fields}</span>
              <span class="form-fill-label">fields filled</span>
            </div>
            <div class="form-fill-bar">
              <div class="form-fill-bar-inner" id="fill-bar"></div>
            </div>
          </div>`;
        this.outputContent.appendChild(entry);
        // Animate counter
        requestAnimationFrame(() => {
          this.counterAnimation(
            document.getElementById('fill-counter'),
            0,
            MOCK_POPULATION.filled_fields,
            1200
          );
          const bar = document.getElementById('fill-bar');
          if (bar) {
            bar.style.width = `${(MOCK_POPULATION.filled_fields / MOCK_POPULATION.total_fields) * 100}%`;
          }
        });
        break;

      case 7:
        entry.innerHTML = `
          <div class="demo-entry-header">
            <span class="demo-entry-step">07</span>
            <span class="demo-entry-title">Submitted</span>
          </div>
          <div class="demo-entry-body">
            <div class="demo-success">
              <div class="demo-success-icon">
                <svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="#55cc58" stroke-width="2">
                  <polyline points="5,10 9,14 15,6"/>
                </svg>
              </div>
              <div>
                <div class="demo-success-text">Pending Insurer Review</div>
                <div class="demo-success-sub">
                  ${MOCK_SUBMISSION.submission_id} &middot; Delivered via ${MOCK_SUBMISSION.delivery_method}
                </div>
              </div>
            </div>
          </div>`;
        this.outputContent.appendChild(entry);
        break;
    }

    // Scroll to bottom
    const outputPanel = document.getElementById('demo-output');
    if (outputPanel) {
      outputPanel.scrollTop = outputPanel.scrollHeight;
    }
  }

  renderEntities() {
    const container = document.getElementById('entities-container');
    if (!container) return;

    MOCK_ENTITIES.forEach((ent, i) => {
      setTimeout(() => {
        const tag = document.createElement('span');
        let typeClass = 'history';
        if (ent.type === 'procedure') typeClass = 'procedure';
        else if (ent.type === 'insurance') typeClass = 'insurance';
        else if (ent.type === 'medication') typeClass = 'medication';

        tag.className = `entity-tag ${typeClass}`;
        tag.innerHTML = `
          <span>${ent.name}</span>
          <span class="entity-type">${ent.type}</span>
        `;
        container.appendChild(tag);
      }, i * 150);
    });
  }

  typewriterEffect(el, text, speed) {
    if (!el) return;
    let i = 0;
    el.innerHTML = '<span class="typewriter-cursor"></span>';

    const type = () => {
      if (i < text.length && this.isRunning) {
        el.innerHTML = text.substring(0, i + 1) + '<span class="typewriter-cursor"></span>';
        i++;
        setTimeout(type, speed);
      } else if (el.querySelector('.typewriter-cursor')) {
        // Remove cursor after done
        setTimeout(() => {
          const cursor = el.querySelector('.typewriter-cursor');
          if (cursor) cursor.remove();
        }, 1000);
      }
    };
    type();
  }

  counterAnimation(el, from, to, duration) {
    if (!el) return;
    const start = performance.now();

    const animate = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = Math.round(from + (to - from) * eased);
      el.textContent = current;

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };
    requestAnimationFrame(animate);
  }
}

// ===== REVEAL.JS INITIALIZATION =====

let demo = null;

Reveal.initialize({
  hash: true,
  width: 1920,
  height: 1080,
  margin: 0.06,
  center: true,
  transition: 'slide',
  backgroundTransition: 'fade',
  plugins: [RevealNotes],
  keyboard: true,
  overview: true,
  progress: true,
  controls: true,
  controlsLayout: 'bottom-right',
}).then(() => {
  demo = new PipelineDemo();

  Reveal.on('slidechanged', (event) => {
    // Reset demo when leaving demo slide
    if (demo && event.previousSlide && event.previousSlide.dataset.state === 'demo-slide') {
      demo.reset();
    }
  });
});
