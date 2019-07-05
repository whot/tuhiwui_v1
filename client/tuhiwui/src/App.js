import React from 'react';
import logo from './logo.svg';
import './App.css';

class Drawing extends React.Component {
  constructor(props) {
    super(props);
    this.state = props.drawing;
    this.svg_scale = 100;
  }

  points(stroke) {
    const points = stroke.points.map((p) =>
      ' ' +  p.position[0]/this.svg_scale + ' ' + p.position[1]/this.svg_scale
    );
    return "M " + points.join(' ');
  }

  strokes() {
    const stroke = this.state.strokes.map((s) =>
      <g><path stroke="black" stroke-width="2" style={{fill: "none"}} d={this.points(s)} />
       </g>
    );
    return stroke;
  }

  svg() {
    const width = this.state.dimensions[0]/this.svg_scale;
    const height = this.state.dimensions[1]/this.svg_scale;
    return (
      <svg baseProfile="full" height={height} version="1.1" width={width}>
        <defs />
        {this.strokes()}
      </svg>
    );
  }

  render() {
    return (
      <div className="drawing">
        <div className="timestamp">{this.state.timestamp}</div>
        <div className="svg">
          {this.svg()}
        </div>
      </div>
    );
  }
}

class Device extends React.Component {
  constructor(props) {
    super(props);
    this.state = {"name": "unknown"}
  }

  renderDrawing(d) {
    return <Drawing drawing={d} />
  }

  renderDrawings() {
    const drawings = this.state.drawings.map((d) =>
      <div>{this.renderDrawing(d)}</div>
    );

    return <div>{drawings}</div>
  }

  render() {
    if (this.state.drawings) {
      return (
        <div>
          <div className="board">
            {this.renderDrawings()}
          </div>
        </div>
      )
    } else {
      return <div>No drawings avaialble</div>
    }
  }

  componentDidMount() {
    const data = this.props.data;
    this.setState(data);
  }
}

class Devices extends React.Component {
  constructor(props) {
    super(props);
  }

  render() {
    if (this.props.devices[0]) {
      return (
        <div class="device">
          <Device data={this.props.devices[0]} />
        </div>
      )
    } else {
        return <div>Loading...</div>
    }
  }

}

class DeviceList extends React.Component {
  constructor(props) {
    super(props);
  }

  render() {
    const devices = this.props.devices.map((d) =>
      <div className="devicename">{d.name}</div>
    );
    return devices;
  }
}

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {"devices": []}
  }

  render() {
    return (
      <div className="App">
        <div className="App-header">
            <div id="logo">Tuhi WUI</div>
            <DeviceList devices={this.state.devices} />
        </div>
        <div id="main">
            <Devices devices={this.state.devices}/>
        </div>
      </div>
    );
  }

  componentDidMount() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "http://localhost:8080/v2/devices", true)
    xhr.onload = function(e) {
      if (xhr.readyState === 4 && xhr.status === 200) {
        var json_obj = JSON.parse(xhr.responseText);
        this.setState({ devices: json_obj });
      }
    }.bind(this);
    xhr.onerror = function (e) {
      console.error(xhr.statusText);
    };
    xhr.send(null);
  }
}

export default App;

// vim: set expandtab tabstop=4 shiftwidth=2: */
