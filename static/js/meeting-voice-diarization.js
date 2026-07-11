/**
 * Case PM — Browser voice diarization with learnable speaker profiles.
 * Uses pitch + spectral features (no cloud ML). Profiles improve when users correct tags.
 */
(function (global) {
  'use strict';

  const MAX_SPEAKERS = 12;
  const MAX_SAMPLES_PER_SPEAKER = 40;
  const MATCH_THRESHOLD = 0.55;
  const NEW_SPEAKER_THRESHOLD = 0.72;
  const SPEAKER_COLORS = ['#6366f1', '#f59e0b', '#14b8a6', '#ec4899', '#22c55e', '#0ea5e9', '#f97316', '#a855f7', '#84cc16', '#06b6d4', '#e11d48', '#78716c'];

  function storageKey(projectId) {
    return `casepm_voice_profiles_p${projectId || 'global'}`;
  }

  function loadProjectProfiles(projectId) {
    try {
      const raw = localStorage.getItem(storageKey(projectId));
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }

  function saveProjectProfiles(projectId, speakers) {
    try {
      const trained = (speakers || []).filter((s) => s.voice_profile?.trained_count > 0);
      if (!trained.length) return;
      localStorage.setItem(storageKey(projectId), JSON.stringify({
        project_id: projectId,
        speakers: trained.map((s) => ({
          id: s.id, label: s.label, name: s.name, color: s.color,
          voice_profile: s.voice_profile,
        })),
        updated_at: new Date().toISOString(),
      }));
    } catch (_) {}
  }

  function emptyProfile() {
    return { samples: [], pitch_mean: 0, pitch_std: 0, centroid_mean: 0, energy_ratio: 0, trained_count: 0, confidence: 0 };
  }

  function ensureProfile(speaker) {
    if (!speaker.voice_profile) speaker.voice_profile = emptyProfile();
    return speaker.voice_profile;
  }

  function fingerprintDistance(a, b) {
    if (!a || !b) return 1;
    const pitchA = a.pitch_hz || 0;
    const pitchB = b.pitch_hz || 0;
    let pitchDist = 1;
    if (pitchA > 0 && pitchB > 0) {
      pitchDist = Math.min(1, Math.abs(pitchA - pitchB) / Math.max(pitchA, pitchB));
    }
    const centA = a.spectral_centroid || 0;
    const centB = b.spectral_centroid || 0;
    let centDist = 1;
    if (centA > 0 && centB > 0) {
      centDist = Math.min(1, Math.abs(centA - centB) / Math.max(centA, centB));
    }
    const erA = a.energy_ratio || 0;
    const erB = b.energy_ratio || 0;
    const erDist = Math.min(1, Math.abs(erA - erB));
    return pitchDist * 0.45 + centDist * 0.35 + erDist * 0.2;
  }

  function profileDistance(fp, profile) {
    if (!profile?.trained_count) return 1;
    const avg = {
      pitch_hz: profile.pitch_mean,
      spectral_centroid: profile.centroid_mean,
      energy_ratio: profile.energy_ratio,
    };
    return fingerprintDistance(fp, avg);
  }

  function updateProfileStats(profile) {
    const samples = profile.samples || [];
    if (!samples.length) return;
    const pitches = samples.map((s) => s.pitch_hz).filter((p) => p > 0);
    const cents = samples.map((s) => s.spectral_centroid).filter((c) => c > 0);
    const ratios = samples.map((s) => s.energy_ratio).filter((r) => r >= 0);
    if (pitches.length) {
      profile.pitch_mean = pitches.reduce((a, b) => a + b, 0) / pitches.length;
      const variance = pitches.reduce((s, p) => s + (p - profile.pitch_mean) ** 2, 0) / pitches.length;
      profile.pitch_std = Math.sqrt(variance);
    }
    if (cents.length) profile.centroid_mean = cents.reduce((a, b) => a + b, 0) / cents.length;
    if (ratios.length) profile.energy_ratio = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    profile.trained_count = samples.length;
    profile.confidence = Math.min(1, 0.35 + samples.length * 0.04);
  }

  function addTrainingSample(speaker, fingerprint) {
    if (!speaker || !fingerprint) return;
    const profile = ensureProfile(speaker);
    profile.samples.push({ ...fingerprint, at: Date.now() });
    if (profile.samples.length > MAX_SAMPLES_PER_SPEAKER) profile.samples.shift();
    updateProfileStats(profile);
  }

  function createSpeakerEngine() {
    let speakers = [];
    let activeSpeakerId = null;
    let autoDetect = true;
    let analyser = null;
    let audioContext = null;
    let freqData = null;
    let recordingStartMs = null;

    function setAnalyser(ctx, analyserNode) {
      audioContext = ctx;
      analyser = analyserNode;
      if (analyser) freqData = new Uint8Array(analyser.frequencyBinCount);
    }

    function setRecordingStart(ms) {
      recordingStartMs = ms;
    }

    function audioOffsetMs() {
      return recordingStartMs ? Date.now() - recordingStartMs : 0;
    }

    function estimatePitch(timeBuf, sampleRate) {
      if (!timeBuf?.length) return null;
      let bestLag = -1;
      let bestCorr = 0;
      const minLag = Math.floor(sampleRate / 400);
      const maxLag = Math.min(Math.floor(sampleRate / 70), timeBuf.length - 1);
      for (let lag = minLag; lag < maxLag; lag++) {
        let corr = 0;
        for (let i = 0; i < timeBuf.length - lag; i++) corr += timeBuf[i] * timeBuf[i + lag];
        if (corr > bestCorr) { bestCorr = corr; bestLag = lag; }
      }
      if (bestLag <= 0 || bestCorr < 0.008) return null;
      return sampleRate / bestLag;
    }

    function captureFingerprint() {
      if (!analyser || !audioContext) return null;
      const timeBuf = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(timeBuf);
      const pitch = estimatePitch(timeBuf, audioContext.sampleRate);
      analyser.getByteFrequencyData(freqData);
      let weightedSum = 0;
      let total = 0;
      let low = 0;
      let mid = 0;
      let high = 0;
      const binHz = audioContext.sampleRate / analyser.fftSize;
      for (let i = 0; i < freqData.length; i++) {
        const mag = freqData[i];
        const hz = i * binHz;
        total += mag;
        weightedSum += hz * mag;
        if (hz < 500) low += mag;
        else if (hz < 2000) mid += mag;
        else high += mag;
      }
      const centroid = total > 0 ? weightedSum / total : 0;
      const denom = low + mid + high || 1;
      return {
        pitch_hz: pitch,
        spectral_centroid: centroid,
        energy_ratio: mid / denom,
        energy_low: low / denom,
        energy_high: high / denom,
        captured_at: Date.now(),
      };
    }

    function initSpeakers(defaultSpeakers, projectId) {
      speakers = JSON.parse(JSON.stringify(defaultSpeakers || []));
      speakers.forEach((s) => ensureProfile(s));
      const saved = loadProjectProfiles(projectId);
      if (saved?.speakers?.length) {
        saved.speakers.forEach((savedSp) => {
          let local = speakers.find((s) => s.id === savedSp.id || (savedSp.name && s.name === savedSp.name));
          if (!local && savedSp.voice_profile?.trained_count > 0) {
            local = { ...savedSp, label: savedSp.label || savedSp.name || `Person ${speakers.length + 1}` };
            speakers.push(local);
          } else if (local && savedSp.voice_profile?.trained_count > 0) {
            local.voice_profile = savedSp.voice_profile;
            if (savedSp.name) local.name = savedSp.name;
          }
        });
      }
      if (!speakers.length) {
        speakers.push({ id: 'sp1', label: 'Person 1', name: '', color: SPEAKER_COLORS[0], voice_profile: emptyProfile() });
      }
      activeSpeakerId = speakers[0].id;
      return speakers;
    }

    function getSpeakers() { return speakers; }

    function getActiveSpeakerId() { return activeSpeakerId; }

    function setActiveSpeakerId(id) {
      if (speakers.find((s) => s.id === id)) activeSpeakerId = id;
    }

    function setAutoDetect(on) { autoDetect = !!on; }

    function speakerLabel(sp) {
      return sp?.name || sp?.label || 'Speaker';
    }

    function nextSpeakerId() {
      let n = 1;
      while (speakers.find((s) => s.id === `sp${n}`)) n++;
      return `sp${n}`;
    }

    function createSpeaker(fingerprint) {
      if (speakers.length >= MAX_SPEAKERS) return speakers[0];
      const id = nextSpeakerId();
      const n = speakers.length + 1;
      const sp = {
        id,
        label: `Person ${n}`,
        name: '',
        color: SPEAKER_COLORS[(n - 1) % SPEAKER_COLORS.length],
        voice_profile: emptyProfile(),
      };
      if (fingerprint) addTrainingSample(sp, fingerprint);
      speakers.push(sp);
      return sp;
    }

    function matchSpeaker(fingerprint) {
      if (!fingerprint) return { speakerId: activeSpeakerId, confidence: 0, isNew: false };
      let bestId = null;
      let bestDist = Infinity;
      speakers.forEach((sp) => {
        const profile = sp.voice_profile;
        if (!profile?.trained_count) return;
        const dist = profileDistance(fingerprint, profile);
        if (dist < bestDist) { bestDist = dist; bestId = sp.id; }
      });
      const confidence = bestId ? Math.max(0, 1 - bestDist) : 0;
      if (bestId && bestDist < MATCH_THRESHOLD) {
        return { speakerId: bestId, confidence, isNew: false, distance: bestDist };
      }
      if (!bestId || bestDist > NEW_SPEAKER_THRESHOLD) {
        return { speakerId: null, confidence: 0, isNew: true, distance: bestDist };
      }
      return { speakerId: bestId, confidence, isNew: false, distance: bestDist };
    }

    function autoAssignSpeaker(fingerprint) {
      if (!autoDetect) return activeSpeakerId;
      const match = matchSpeaker(fingerprint);
      if (match.isNew && speakers.length < MAX_SPEAKERS) {
        const sp = createSpeaker(fingerprint);
        activeSpeakerId = sp.id;
        return sp.id;
      }
      if (match.speakerId) {
        activeSpeakerId = match.speakerId;
        const sp = speakers.find((s) => s.id === match.speakerId);
        if (sp && match.confidence > 0.5) addTrainingSample(sp, fingerprint);
        return match.speakerId;
      }
      const active = speakers.find((s) => s.id === activeSpeakerId);
      if (active) addTrainingSample(active, fingerprint);
      return activeSpeakerId;
    }

    function trainFromCorrection(speakerId, fingerprint) {
      const sp = speakers.find((s) => s.id === speakerId);
      if (sp && fingerprint) addTrainingSample(sp, fingerprint);
    }

    function reprocessSegments(segments) {
      return (segments || []).map((seg) => {
        const fp = seg.voice_fingerprint;
        if (!fp) return seg;
        const match = matchSpeaker(fp);
        if (match.speakerId && match.confidence >= 0.45) {
          const sp = speakers.find((s) => s.id === match.speakerId);
          return {
            ...seg,
            speaker_id: match.speakerId,
            speaker_label: speakerLabel(sp),
            auto_assigned: true,
            confidence: match.confidence,
          };
        }
        return seg;
      });
    }

    function renameSpeaker(speakerId, name) {
      const sp = speakers.find((s) => s.id === speakerId);
      if (sp) {
        sp.name = (name || '').trim();
        return speakerLabel(sp);
      }
      return null;
    }

    function persistProfiles(projectId) {
      saveProjectProfiles(projectId, speakers);
    }

    return {
      MAX_SPEAKERS,
      setAnalyser,
      setRecordingStart,
      audioOffsetMs,
      captureFingerprint,
      initSpeakers,
      getSpeakers,
      getActiveSpeakerId,
      setActiveSpeakerId,
      setAutoDetect,
      speakerLabel,
      createSpeaker,
      matchSpeaker,
      autoAssignSpeaker,
      trainFromCorrection,
      reprocessSegments,
      renameSpeaker,
      addTrainingSample,
      persistProfiles,
      loadProjectProfiles,
      trainFromTranscriptReview,
      runVoiceSelfTest,
    };
  }

  /** Batch-train profiles from user-corrected transcript lines. */
  function trainFromTranscriptReview(engine, segments) {
    if (!engine) return { trained: 0 };
    let trained = 0;
    (segments || []).forEach((seg) => {
      if (seg.user_corrected && seg.voice_fingerprint && seg.speaker_id) {
        engine.trainFromCorrection(seg.speaker_id, seg.voice_fingerprint);
        trained++;
      }
    });
    return { trained };
  }

  /**
   * Synthetic two-voice self-test — trains two profiles then verifies matching.
   * Uses pitch/spectral fingerprints (no external audio file required).
   */
  function runVoiceSelfTest(engine) {
    if (!engine) return { accuracy: 0, correct: 0, total: 0, details: [], error: 'No engine' };
    const speakers = engine.getSpeakers();
    const spA = speakers[0] || engine.createSpeaker(null);
    let spB = speakers[1];
    if (!spB || spB.id === spA.id) spB = engine.createSpeaker(null);

    const fpA = { pitch_hz: 142, spectral_centroid: 820, energy_ratio: 0.38 };
    const fpB = { pitch_hz: 218, spectral_centroid: 1240, energy_ratio: 0.56 };
    for (let i = 0; i < 6; i++) {
      engine.trainFromCorrection(spA.id, {
        pitch_hz: fpA.pitch_hz + (i - 3) * 4,
        spectral_centroid: fpA.spectral_centroid + i * 8,
        energy_ratio: fpA.energy_ratio,
      });
      engine.trainFromCorrection(spB.id, {
        pitch_hz: fpB.pitch_hz + (i - 3) * 5,
        spectral_centroid: fpB.spectral_centroid + i * 10,
        energy_ratio: fpB.energy_ratio,
      });
    }

    const tests = [
      { fp: fpA, expect: spA.id, label: 'Speaker A baseline' },
      { fp: fpB, expect: spB.id, label: 'Speaker B baseline' },
      { fp: { pitch_hz: 148, spectral_centroid: 850, energy_ratio: 0.4 }, expect: spA.id, label: 'Speaker A variant' },
      { fp: { pitch_hz: 210, spectral_centroid: 1210, energy_ratio: 0.54 }, expect: spB.id, label: 'Speaker B variant' },
    ];
    let correct = 0;
    const details = tests.map((t) => {
      const m = engine.matchSpeaker(t.fp);
      const ok = m.speakerId === t.expect;
      if (ok) correct++;
      return { ok, label: t.label, expected: t.expect, got: m.speakerId, confidence: m.confidence };
    });
    return { accuracy: correct / tests.length, correct, total: tests.length, details };
  }

  global.CasePMVoiceDiarization = {
    createSpeakerEngine,
    loadProjectProfiles,
    saveProjectProfiles,
    SPEAKER_COLORS,
    trainFromTranscriptReview,
    runVoiceSelfTest,
  };
})(window);
