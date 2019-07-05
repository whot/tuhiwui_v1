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
      <div className="Drawing">
        <div className="Timestamp">{this.state.timestamp}</div>
        {this.svg()}
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
    return <div><Drawing drawing={d} /></div>;
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
        <div id="board">
          {this.state.name} - {this.state.id}

          <div className="board-row">
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
    this.state = {"devices": []}
  }

  render() {
    if (this.state.devices[0]) {
      return (
        <div class="device">
          <Device data={this.state.devices[0]} />
        </div>
      )
    } else {
        return <div>Loading...</div>
    }
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

function App() {
  return (
    <div className="App">
      <div id="header" >
        <header className="App-header">
          <img src={logo} className="App-logo" alt="logo" />
        <p>Tuhi WUI</p>
        </header>
      </div>
      <div id="main">
          <Devices />
      </div>
    </div>
  );
}

export default App;

// vim: set expandtab tabstop=4 shiftwidth=2: */
