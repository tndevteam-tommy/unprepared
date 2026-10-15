"""GLSL 1.20 per-pixel lighting used for the 3D pass (compatibility profile, so the
immediate-mode geometry and matrix stack keep working unchanged)."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from OpenGL.GL import (GL_COMPILE_STATUS, GL_FRAGMENT_SHADER, GL_LINK_STATUS, GL_VERTEX_SHADER, glAttachShader,
                       glCompileShader, glCreateProgram, glCreateShader, glGetProgramInfoLog, glGetProgramiv,
                       glGetShaderInfoLog, glGetShaderiv, glGetUniformLocation, glLinkProgram, glShaderSource,
                       glUniform1f, glUniform1i, glUniform3f, glUniform3fv, glUniform1fv, glUseProgram)

MAX_POINT_LIGHTS = 8

VERTEX_SHADER = """
#version 120
varying vec3 vEyePos;
varying vec3 vNormal;
varying vec2 vTexCoord;
void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    vEyePos = eye.xyz;
    vNormal = normalize(gl_NormalMatrix * gl_Normal);
    vTexCoord = gl_MultiTexCoord0.xy;
    gl_Position = gl_ProjectionMatrix * eye;
}
"""

FRAGMENT_SHADER = """
#version 120
#define MAX_LIGHTS %d
uniform sampler2D uTexture;
uniform int uUseTexture;
uniform vec3 uColor;
uniform vec3 uEmission;
uniform float uFogStrength;
uniform float uContrast;
uniform float uAlpha;
uniform vec3 uSunDir;       // eye space, towards the sun
uniform vec3 uSunColor;
uniform vec3 uMoonDir;
uniform vec3 uMoonColor;
uniform vec3 uAmbient;
uniform int uNumLights;
uniform vec3 uLightPos[MAX_LIGHTS];     // eye space
uniform vec3 uLightColor[MAX_LIGHTS];
uniform float uLightRange[MAX_LIGHTS];
uniform vec3 uFogColor;
uniform float uFogDensity;
varying vec3 vEyePos;
varying vec3 vNormal;
varying vec2 vTexCoord;

void main() {
    vec3 n = normalize(vNormal);
    vec3 base = uColor;
    float alpha = 1.0;
    if (uUseTexture == 1) {
        vec4 texel = texture2D(uTexture, vTexCoord);
        base *= texel.rgb;
        alpha = texel.a;
    }

    vec3 light = uAmbient;
    light += uSunColor * max(dot(n, normalize(uSunDir)), 0.0);
    light += uMoonColor * max(dot(n, normalize(uMoonDir)), 0.0);
    for (int i = 0; i < MAX_LIGHTS; i++) {
        if (i >= uNumLights) break;
        vec3 toLight = uLightPos[i] - vEyePos;
        float dist = length(toLight);
        float atten = clamp(1.0 - dist / uLightRange[i], 0.0, 1.0);
        atten = atten * (2.0 - atten);            // bright near the flame, soft fall-off
        float ndl = max(dot(n, toLight / max(dist, 0.001)), 0.0);
        light += uLightColor[i] * (ndl * 0.8 + 0.2) * atten;
    }
    vec3 color = base * light + uEmission * base;
    color = (color - vec3(0.5)) * uContrast + vec3(0.5);

    float dist = length(vEyePos);
    float f = exp(-(uFogDensity * dist) * (uFogDensity * dist));
    f = clamp(f, 0.0, 1.0);
    f = mix(1.0, f, uFogStrength);
    gl_FragColor = vec4(mix(uFogColor, color, f), alpha * uAlpha);
}
""" % MAX_POINT_LIGHTS


class ShaderError(RuntimeError):
    pass


def _compile(kind, source: str):
    shader = glCreateShader(kind)
    glShaderSource(shader, source)
    glCompileShader(shader)
    if not glGetShaderiv(shader, GL_COMPILE_STATUS):
        raise ShaderError(glGetShaderInfoLog(shader))
    return shader


class LightingShader:
    """Wraps the lighting program and caches uniform locations."""

    def __init__(self):
        self.program = glCreateProgram()
        glAttachShader(self.program, _compile(GL_VERTEX_SHADER, VERTEX_SHADER))
        glAttachShader(self.program, _compile(GL_FRAGMENT_SHADER, FRAGMENT_SHADER))
        glLinkProgram(self.program)
        if not glGetProgramiv(self.program, GL_LINK_STATUS):
            raise ShaderError(glGetProgramInfoLog(self.program))
        self._loc: Dict[str, int] = {}
        self.active = False

    def loc(self, name: str) -> int:
        if name not in self._loc:
            self._loc[name] = glGetUniformLocation(self.program, name)
        return self._loc[name]

    def use(self) -> None:
        glUseProgram(self.program)
        self.active = True
        glUniform1i(self.loc("uTexture"), 0)
        glUniform1f(self.loc("uContrast"), 1.0)
        glUniform1f(self.loc("uAlpha"), 1.0)

    def set_contrast(self, contrast: float) -> None:
        glUniform1f(self.loc("uContrast"), contrast)

    def set_alpha(self, alpha: float) -> None:
        glUniform1f(self.loc("uAlpha"), alpha)

    def stop(self) -> None:
        glUseProgram(0)
        self.active = False

    # --- per-frame ---------------------------------------------------------------
    def set_atmosphere(self, sun_dir_eye, sun_color, moon_dir_eye, moon_color, ambient, fog_color, fog_density) -> None:
        glUniform3f(self.loc("uSunDir"), *sun_dir_eye)
        glUniform3f(self.loc("uSunColor"), *sun_color)
        glUniform3f(self.loc("uMoonDir"), *moon_dir_eye)
        glUniform3f(self.loc("uMoonColor"), *moon_color)
        glUniform3f(self.loc("uAmbient"), *ambient)
        glUniform3f(self.loc("uFogColor"), *fog_color)
        glUniform1f(self.loc("uFogDensity"), fog_density)

    def set_point_lights(self, lights: Sequence) -> None:
        """``lights``: sequence of (eye_pos(3), color(3), range)."""
        lights = list(lights)[:MAX_POINT_LIGHTS]
        glUniform1i(self.loc("uNumLights"), len(lights))
        if lights:
            pos = [c for l in lights for c in l[0]]
            col = [c for l in lights for c in l[1]]
            rng = [l[2] for l in lights]
            glUniform3fv(self.loc("uLightPos"), len(lights), pos)
            glUniform3fv(self.loc("uLightColor"), len(lights), col)
            glUniform1fv(self.loc("uLightRange"), len(lights), rng)

    # --- per-object ----------------------------------------------------------------
    def set_material(self, color=(1.0, 1.0, 1.0), emission=(0.0, 0.0, 0.0), textured: bool = True,
                     fog_strength: float = 1.0) -> None:
        glUniform3f(self.loc("uColor"), *color)
        glUniform3f(self.loc("uEmission"), *emission)
        glUniform1i(self.loc("uUseTexture"), 1 if textured else 0)
        glUniform1f(self.loc("uFogStrength"), fog_strength)


def try_create_lighting_shader() -> Optional[LightingShader]:
    try:
        return LightingShader()
    except Exception:   # no GLSL support: the renderer falls back to fixed-function lighting
        return None
